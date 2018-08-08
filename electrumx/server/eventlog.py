# -*- coding: utf-8 -*-
"""
__author__ = 'CodeFace'
"""
import array
import ast
import bisect
from collections import defaultdict
from functools import partial
from struct import pack, unpack

import electrumx.lib.util as util
from electrumx.lib.hash import hash_to_hex_str, HASHX_LEN


class Eventlog(object):

    DB_VERSIONS = [0]

    def __init__(self):
        self.logger = util.class_logger(__name__, self.__class__.__name__)
        # For history compaction
        self.max_hist_row_entries = 12500
        self.unflushed = defaultdict(partial(array.array, 'I'))
        self.unflushed_count = 0
        self.db = None

    def open_db(self, db_class, for_sync, utxo_flush_count):
        self.db = db_class('eventlog', for_sync)
        self.read_state()
        self.clear_excess(utxo_flush_count)
        return self.flush_count

    def close_db(self):
        if self.db:
            self.db.close()
            self.db = None

    def read_state(self):
        state = self.db.get(b'state')
        if not state:
            self.flush_count = 0
            self.db_version = max(self.DB_VERSIONS)
        else:
            state = ast.literal_eval(state.decode())
            if not isinstance(state, dict):
                raise RuntimeError('failed reading state from eventlog DB')
            self.flush_count = state.get('eventlog_flush_count', 0)
            self.db_version = state.get('db_version', 0)

        self.logger.info(f'eventlog DB version: {self.db_version}')

    def write_state(self, batch):
        '''Write eventlog state to the batch.'''
        state = {
            'eventlog_flush_count': self.flush_count,
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
        eventlogs: {b'hashY' => [array('I', [txnum, log_index]),]}
        """
        self.unflushed.update(eventlogs)
        count = sum(len(x) for x in eventlogs.values())
        self.unflushed_count += count

    def flush(self):
        self.flush_count += 1
        flush_id = pack('>H', self.flush_count)
        unflushed = self.unflushed
        with self.db.write_batch() as batch:
            for hashY in sorted(unflushed):
                key = hashY + flush_id
                # 把二维数据按照一维数组存储
                batch.put(key, b''.join([x.tobytes() for x in unflushed[hashY]]))
            self.write_state(batch)

        count = len(unflushed)
        unflushed.clear()
        self.unflushed_count = 0
        return count

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
                    a = array.array('I')
                    a.frombytes(hist)  # txnum, log_index
                    tx_nums = array.array('I', [a[2*i] for i in range(len(a)//2)])
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

        return nremoves

    def get_txnums(self, key, limit=1000):
        limit = util.resolve_limit(limit)
        for key, hist in self.db.iterator(prefix=key):
            a = array.array('I')
            a.frombytes(hist)
            # 把一维数据恢复成2*2维
            for i in range(len(a)//2):
                if limit == 0:
                    return
                tx_num, log_index = a[2*i: 2*i+2]
                yield tx_num, log_index
                limit -= 1