#!/usr/bin/python3

import re, telnetlib, sys
import datetime

class MemcachedStats:

    _client = None
    _key_regex = re.compile(r'ITEM (.*) \[(.*); (.*)\]')
    _slab_regex = re.compile(r'STAT items:(.*):number')
    _stat_regex = re.compile(r"STAT (.*) (.*)\r")

    def __init__(self, host='localhost', port='11211'):
        self._host = host
        self._port = port

    @property
    def client(self):
        if self._client is None:
            self._client = telnetlib.Telnet(self._host, self._port)
        return self._client

    def command(self, cmd):
        ' Write a command to telnet and return the response '
        bcmd = (cmd + '\n').encode('ascii')
        self.client.write(bcmd)
        bret = self.client.read_until(b'END')
        return bret.decode('utf-8')

    def key_details(self, sort=True, limit=100):
        ' Return a list of tuples containing keys and details '
        cmd = 'stats cachedump %s %s'
        keys = [key for id in self.slab_ids()
            for key in self._key_regex.findall(self.command(cmd % (id, limit)))]
        if sort:
            return sorted(keys)
        else:
            return keys

    def keys(self, sort=True, limit=100):
        ' Return a list of keys in use '
        key_list = []
        keys = self.key_details(sort=sort, limit=limit)
        for key in keys:
            name, length, expiry = key
            expiry = int(expiry.split(' ')[0])
            if expiry:
                expire = datetime.datetime.fromtimestamp(expiry)
                now    = datetime.datetime.now()
                delta = expire - now
                expiry = delta.seconds
            if expiry >= 0: # not already expired
                key_list.append((name, expiry))

        return key_list
        #return [key[0] for key in self.key_details(sort=sort, limit=limit)]

    def slab_ids(self):
        ' Return a list of slab ids in use '
        slabids = self._slab_regex.findall(self.command('stats items'))
        return list(set(slabids))   # make sure they are unique


    def stats(self):
        ' Return a dict containing memcached stats '
        return dict(self._stat_regex.findall(self.command('stats')))


    def get_values(self, key_list):
        bkeys_only = [key for key, expire in key_list]
        cmd = 'get ' + ' '.join(bkeys_only)
        results = self.command(cmd).splitlines()
        key_vals = []
        for i in range(0, len(key_list)):
            line = results[(i * 2) + 1].split(' ')
            data = results[(i * 2) + 2]
            if line[0] != 'VALUE':
                print('Wrong value')
            original_key, expiry = key_list[i]
            if line[1] != original_key:
                print('Key values dont match: ' + line[1] + ' != ' + original_key)
            key_vals.append((original_key, int(line[2]), expiry, int(line[3]), data))
        return key_vals




def main(argv=None):
    if not argv:
        argv = sys.argv
    host = argv[1] if len(argv) >= 2 else '127.0.0.1'
    port = argv[2] if len(argv) >= 3 else '11211'
    import pprint
    m = MemcachedStats(host, port)
    keys = m.keys(limit=0)
    pprint.pprint(m.get_values(keys))

if __name__ == '__main__':
    main()
