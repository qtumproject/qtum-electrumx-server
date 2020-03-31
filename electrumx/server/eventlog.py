# -*- coding: utf-8 -*-
"""
__author__ = 'CodeFace'
"""
import time
import array
import ast
import bisect
from collections import defaultdict
from functools import partial
from struct import pack, unpack

import electrumx.lib.util as util
from electrumx.lib.util import pack_be_uint16, unpack_be_uint16_from
from electrumx.lib.hash import hash_to_hex_str, HASHY_LEN, TOPIC_LEN


class Eventlog(object):

    DB_VERSIONS = [1]

    def __init__(self):
        self.logger = util.class_logger(__name__, self.__class__.__name__)
        # For history compaction
        self.max_hist_row_entries = 12500
        self.unflushed = defaultdict(list)  # {b'hashY_topic' => [array('Q', [txnum, log_index]),]}
        self.unflushed_count = 0
        self.flush_count = 0
        self.comp_flush_count = -1
        self.comp_cursor = -1
        self.db_version = max(self.DB_VERSIONS)
        self.db = None

    def open_db(self, db_class, for_sync, utxo_flush_count, compacting):
        self.db = db_class('eventlog', for_sync)
        self.read_state()
        self.clear_excess(utxo_flush_count)
        # An incomplete compaction needs to be cancelled otherwise
        # restarting it will corrupt the history
        if not compacting:
            self._cancel_compaction()
        return self.flush_count

    def close_db(self):
        if self.db:
            self.db.close()
            self.db = None

    def read_state(self):
        state = self.db.get(b'state')
        if not state:
            self.flush_count = 0
            self.comp_flush_count = -1
            self.comp_cursor = -1
            self.db_version = max(self.DB_VERSIONS)
        else:
            state = ast.literal_eval(state.decode())
            if not isinstance(state, dict):
                raise RuntimeError('failed reading state from eventlog DB')
            self.flush_count = state.get('eventlog_flush_count', 0)
            self.comp_flush_count = state.get('comp_flush_count', -1)
            self.comp_cursor = state.get('comp_cursor', -1)
            self.db_version = state.get('db_version', 0)

        self.logger.info(f'eventlog DB version: {self.db_version}')
        if self.db_version not in self.DB_VERSIONS:
            msg = f'this software only handles DB versions {self.DB_VERSIONS}'
            self.logger.error(msg)
            raise RuntimeError(msg)
        self.logger.info(f'eventlog flush count: {self.flush_count:,d}')

    def write_state(self, batch):
        '''Write eventlog state to the batch.'''
        state = {
            'eventlog_flush_count': self.flush_count,
            'comp_flush_count': self.comp_flush_count,
            'comp_cursor': self.comp_cursor,
            'db_version': self.db_version,
        }
        batch.put(b'state', repr(state).encode())

    def clear_excess(self, utxo_flush_count):
        # < might happen at end of compaction as both DBs cannot be
        # updated atomically
        if self.flush_count <= utxo_flush_count:
            return

        self.logger.info('DB shut down uncleanly.  Scanning for '
                         'excess eventlog flushes...')
        keys = []
        for key, hist in self.db.iterator(prefix=b''):
            flush_id, = unpack('>H', key[-2:])
            if flush_id > utxo_flush_count:
                keys.append(key)

        self.logger.info('deleting {:,d} eventlog entries'.format(len(keys)))
        self.flush_count = utxo_flush_count
        with self.db.write_batch() as batch:
            for key in keys:
                batch.delete(key)
            self.write_state(batch)

        self.logger.info('deleted excess eventlog entries')

    def assert_flushed(self):
        assert not self.unflushed

    def add_unflushed(self, eventlogs):
        """
        eventlogs: {b'hashY_topic' => [array('Q', [txnum, log_index]),]}
        """
        unflushed = self.unflushed
        count = 0
        for hashY_topic in eventlogs:
            datas = eventlogs[hashY_topic]
            for data in datas:
                unflushed[hashY_topic].append(data)
            count += len(datas)
        self.unflushed_count += count

    def unflushed_memsize(self):
        return len(self.unflushed) * 180 + self.unflushed_count * 4

    def flush(self):
        start_time = time.time()
        self.flush_count += 1
        flush_id = pack_be_uint16(self.flush_count)
        unflushed = self.unflushed
        with self.db.write_batch() as batch:
            for hashY_topic in sorted(unflushed):
                key = hashY_topic + flush_id
                # 把二维数据按照一维数组存储
                batch.put(key, b''.join([x.tobytes() for x in unflushed[hashY_topic]]))
            self.write_state(batch)

        count = len(unflushed)
        unflushed.clear()
        self.unflushed_count = 0

        if self.db.for_sync:
            elapsed = time.time() - start_time
            self.logger.info(f'flushed eventlog in {elapsed:.1f}s '
                             f'for {count:,d} addrs')

    def backup(self, hashY_keys, tx_count):
        # Not certain this is needed, but it doesn't hurt
        self.flush_count += 1
        nremoves = 0
        bisect_left = bisect.bisect_left
        self.logger.info('backup_eventlogs')
        with self.db.write_batch() as batch:
            for addr in sorted(hashY_keys):
                deletes = []
                puts = {}
                for key, hist in self.db.iterator(prefix=addr, reverse=True):
                    a = array.array('Q')
                    a.frombytes(hist)  # txnum, log_index
                    tx_nums = array.array('Q', [a[2*i] for i in range(len(a)//2)])
                    # Remove all eventlog entries >= self.tx_count
                    idx = bisect_left(tx_nums, tx_count)
                    nremoves += len(tx_nums) - idx
                    if idx > 0:
                        puts[key] = a[:idx*2].tobytes()
                        break
                    deletes.append(key)
                for key in deletes:
                    batch.delete(key)
                for key, value in puts.items():
                    batch.put(key, value)
                self.logger.info('backup_eventlogs, deletes {}, puts {}'.format(deletes, puts))
            self.write_state(batch)

        self.logger.info(f'backing up removed {nremoves:,d} eventlog entries')

    def get_txnums(self, key, limit=1000):
        limit = util.resolve_limit(limit)
        for key, hist in self.db.iterator(prefix=key):
            a = array.array('Q')
            a.frombytes(hist)
            # 把一维数据恢复成2*2维
            for i in range(len(a)//2):
                if limit == 0:
                    return
                tx_num, log_index = a[2*i: 2*i+2]
                yield tx_num, log_index
                limit -= 1

    def _flush_compaction(self, cursor, write_items, keys_to_delete):
        '''Flush a single compaction pass as a batch.'''
        # Update compaction state
        if cursor == 65536:
            self.flush_count = self.comp_flush_count
            self.comp_cursor = -1
            self.comp_flush_count = -1
        else:
            self.comp_cursor = cursor

        # History DB.  Flush compacted history and updated state
        with self.db.write_batch() as batch:
            # Important: delete first!  The keyspace may overlap.
            for key in keys_to_delete:
                batch.delete(key)
            for key, value in write_items:
                batch.put(key, value)
            self.write_state(batch)

    def _compact_hashY_topic(self, hashY_topic, hist_map, hist_list,
                             write_items, keys_to_delete):
        '''Compres history for a hashY.  hist_list is an ordered list of
        the histories to be compressed.'''
        # History entries (tx numbers) are 4 bytes each.  Distribute
        # over rows of up to 50KB in size.  A fixed row size means
        # future compactions will not need to update the first N - 1
        # rows.
        max_row_size = self.max_hist_row_entries * 4
        full_hist = b''.join(hist_list)
        nrows = (len(full_hist) + max_row_size - 1) // max_row_size
        if nrows > 4:
            self.logger.info('hashY {} is large: {:,d} entries across '
                             '{:,d} rows'
                             .format(hash_to_hex_str(hashY_topic),
                                     len(full_hist) // 4, nrows))

        # Find what history needs to be written, and what keys need to
        # be deleted.  Start by assuming all keys are to be deleted,
        # and then remove those that are the same on-disk as when
        # compacted.
        write_size = 0
        keys_to_delete.update(hist_map)
        for n, chunk in enumerate(util.chunks(full_hist, max_row_size)):
            key = hashY_topic + pack_be_uint16(n)
            if hist_map.get(key) == chunk:
                keys_to_delete.remove(key)
            else:
                write_items.append((key, chunk))
                write_size += len(chunk)

        assert n + 1 == nrows
        self.comp_flush_count = max(self.comp_flush_count, n)

        return write_size

    def _compact_prefix(self, prefix, write_items, keys_to_delete):
        '''Compact all history entries for hashYs beginning with the
        given prefix.  Update keys_to_delete and write.'''
        prior_hashY_topic = None
        hist_map = {}
        hist_list = []

        key_len = HASHY_LEN + TOPIC_LEN + 2
        write_size = 0
        for key, hist in self.db.iterator(prefix=prefix):
            # Ignore non-history entries
            if len(key) != key_len:
                continue
            hashY_topic = key[:-2]
            if hashY_topic != prior_hashY_topic and prior_hashY_topic:
                # print('prior_hashY is', prior_hashY)
                write_size += self._compact_hashY_topic(prior_hashY_topic, hist_map,
                                                        hist_list, write_items,
                                                        keys_to_delete)
                hist_map.clear()
                hist_list.clear()
            prior_hashY_topic = hashY_topic
            hist_map[key] = hist
            hist_list.append(hist)

        if prior_hashY_topic:
            write_size += self._compact_hashY_topic(prior_hashY_topic, hist_map, hist_list,
                                                    write_items, keys_to_delete)
        return write_size

    def _compact_history(self, limit):
        '''Inner loop of history compaction.  Loops until limit bytes have
        been processed.
        '''
        keys_to_delete = set()
        write_items = []   # A list of (key, value) pairs
        write_size = 0

        # Loop over 2-byte prefixes
        cursor = self.comp_cursor
        while write_size < limit and cursor < 65536:
            prefix = pack_be_uint16(cursor)
            write_size += self._compact_prefix(prefix, write_items,
                                               keys_to_delete)
            cursor += 1

        max_rows = self.comp_flush_count + 1
        self._flush_compaction(cursor, write_items, keys_to_delete)

        self.logger.info('eventlog compaction: wrote {:,d} rows ({:.1f} MB), '
                         'removed {:,d} rows, largest: {:,d}, {:.1f}% complete'
                         .format(len(write_items), write_size / 1000000,
                                 len(keys_to_delete), max_rows,
                                 100 * cursor / 65536))
        return write_size

    def _cancel_compaction(self):
        if self.comp_cursor != -1:
            self.logger.warning('cancelling in-progress eventlog compaction')
            self.comp_flush_count = -1
            self.comp_cursor = -1
