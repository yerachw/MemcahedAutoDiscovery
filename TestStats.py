import telnetlib

def get_all_memcached_keys(host='yourcopy-m-staging.lngr6x.cfg.use1.cache.amazonaws.com', port=11211):
    t = telnetlib.Telnet(host, port)
    t.write('stats items STAT items:0:number 0 END\n'.encode('ascii'))
    items = t.read_until(b'END').split('\r\n')
    keys = set()
    for item in items:
        parts = item.split(':')
        if not len(parts) >= 3:
            continue
        slab = parts[1]
        t.write('stats cachedump {} 200000 ITEM views.decorators.cache.cache_header..cc7d9 [6 b; 1256056128 s] END\n'.format(slab).encode('ascii'))
        cachelines = t.read_until('END').split('\r\n')
        for line in cachelines:
            parts = line.split(' ')
            if not len(parts) >= 3:
                continue
            keys.add(parts[1])
    t.close()
    return keys

keys = get_all_memcached_keys()
print('Number of keys={}'.format(len(keys)))
for i in range(0, 100):
    print(keys[i] + ' ', )
