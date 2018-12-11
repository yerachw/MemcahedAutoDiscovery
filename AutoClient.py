#!/usr/bin/python3

import boto3
from pymemcache.client.hash import HashClient
import time
import json
from threading import Event, Thread
import os
import re, telnetlib
import datetime


#https://stackoverflow.com/questions/5730276/how-to-export-all-keys-and-values-from-memcached-with-python-memcache

class MemcachedStats:

    _client = None
    _key_regex = re.compile(r'ITEM (.*) \[(.*); (.*)\]')
    _slab_regex = re.compile(r'STAT items:(.*):number')
    _stat_regex = re.compile(r"STAT (.*) (.*)\r")

    def __init__(self, host, port):
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

    def key_details(self):
        ' Return a list of tuples containing keys and details '
        cmd = 'stats cachedump %s %s'
        keys = [key for id in self.slab_ids() for key in self._key_regex.findall(self.command(cmd % (id, 0)))]
        return keys

    def keys(self):
        ' Return a list of keys in use '
        key_list = []
        keys = self.key_details()
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


class TimerThread(Thread):
    def __init__(self, function):
        Thread.__init__(self)
        self.function = function
        self.event = Event()

    def run(self):
        while not self.event.wait(60):
            self.function()



class AutodiscoveryClient():

    def __init__(self, cluster_id):
        self.elasticache = boto3.client('elasticache', region_name='us-east-1')
        self.cluster_id = cluster_id
        self.servers = self.new_server_list()
        self.internal_scale = False
        self.hash_client = HashClient(self.servers, serializer=self.json_serializer, deserializer=self.json_deserializer, use_pooling=True)
        thread = TimerThread(self.check_cluster)
        thread.start()


    def new_server_list(self):
        new_servers = []
        response = self.elasticache.describe_cache_clusters(CacheClusterId=self.cluster_id, ShowCacheNodeInfo=True)
        self.endpoint = response['CacheClusters'][0]['ConfigurationEndpoint']
        nodes = response['CacheClusters'][0]['CacheNodes']
        for node in nodes:
            if 'Endpoint' in node:  # server may be coming up, no endpoint yet
                endpoint = (node['Endpoint']['Address'], node['Endpoint']['Port'])
                new_servers.append(endpoint)
        return new_servers


    def check_cluster(self):
        print('Checking cluster')
        new_servers = self.new_server_list()

        try:
            new_server_set = set(new_servers)
            cur_server_set = set(self.servers)
            servers_changed = False
            if (new_server_set - cur_server_set) or (cur_server_set - new_server_set):
                print('Found a node difference')
                # self.dump_keys('all_keys.txt')
                servers_changed = True

            if (new_server_set - cur_server_set):
                print('Server added')
                self.internal_scale = False
                self.hash_client = HashClient(new_servers, serializer=self.json_serializer,
                                                  deserializer=self.json_deserializer, use_pooling=True)
                self.remap_keys(self.servers)

            # server removed not with our code
            if (cur_server_set - new_server_set):
                print('Server removed')
                if self.internal_scale:
                    self.internal_scale = False
                else:
                    print('Removing server')
                    self.hash_client = HashClient(new_servers, serializer=self.json_serializer,
                                                  deserializer=self.json_deserializer, use_pooling=True)

            if servers_changed:
                self.servers = new_servers
 #               self.dump_keys('all_keys_2.txt')
                self.internal_scale = False

        except Exception as e:
            print(str(e))



    def json_serializer(self, key, value):
        if type(value) == str:
            return value, 1
        return json.dumps(value), 2


    def json_deserializer(self, key, value, flags):
        if flags == 1:
            return value.decode('utf-8')
        if flags == 2:
            return json.loads(value.decode('utf-8'))
        raise Exception("Unknown serialization format")


    def remap_keys(self, server_list):
 #       self.dump_keys(server_list)
        for endpoint in server_list:
            startTime = int(time.time())
            ip, port = endpoint
            print('Processing ' + ip)
            memcachedStats = MemcachedStats(ip, port)
            key_list = memcachedStats.keys()
            client = HashClient([endpoint], serializer=self.json_serializer,
                                deserializer=self.json_deserializer)
            count = 0
            for key, expiry in key_list:
                if not self.hash_client.get(key):
                    val = client.get(key)
                    if val:
                        self.hash_client.set(key, val, expire=expiry, noreply=True)
                        count = count + 1
            endTime = int(time.time())
            print('Found {} keys. Remapped {} in {} seconds'.format(len(key_list), count, endTime - startTime))



    def dump_keys(self, server_list):
        count = 1
        for endpoint in server_list:
            ip, port = endpoint
            print('Dumping ' + ip)
            command = 'memdump --servers={}:{} > {}.txt'.format(ip, port, count)
            count = count + 1
            os.system(command)


    def add_node(self):
        if self.internal_scale:
            print('Cannot scale more than one at a time')
        try:
            response = self.elasticache.describe_cache_clusters(CacheClusterId=cluster_id, ShowCacheNodeInfo=True)
            count = response['CacheClusters'][0]['NumCacheNodes']
            self.internal_scale = True
            self.elasticache.modify_cache_cluster(CacheClusterId=cluster_id, NumCacheNodes=count + 1,
                                                   ApplyImmediately=True)
            print('Added node {}'.format(count + 1))
        except Exception as e:
            print(str(e))

    def remove_node(self):
        if self.internal_scale:
            print('Cannot scale more than one at a time')
        try:
            self.internal_scale = True
            response = self.elasticache.describe_cache_clusters(CacheClusterId=self.cluster_id, ShowCacheNodeInfo=True)
            count = response['CacheClusters'][0]['NumCacheNodes']
            nodes = response['CacheClusters'][0]['CacheNodes']
            node = nodes[count - 1]
            id_to_remove = node['CacheNodeId']
            endpoint = (node['Endpoint']['Address'], node['Endpoint']['Port'])
            print('Removing node: ' + str(endpoint) + ' with id ' + str(id_to_remove))

            new_servers = self.servers.copy()
            new_servers.remove(endpoint)
            print('Remaining servers: ' + str(new_servers))
            self.hash_client = HashClient(new_servers, serializer=self.json_serializer,
                                          deserializer=self.json_deserializer, use_pooling=True)

            self.remap_keys(self.servers)

            # remove the node
            response = self.elasticache.modify_cache_cluster(CacheClusterId=self.cluster_id, NumCacheNodes=count - 1, CacheNodeIdsToRemove=[id_to_remove], ApplyImmediately=True)
            print(response)

        except Exception as e:
            print(str(e))


cluster_id = 'scale-test'
memcached = AutodiscoveryClient(cluster_id)


def setVariable(variable_name, variable_value, expire_secs=0):
    try:
        return memcached.hash_client.set(key=variable_name, value=variable_value, expire=expire_secs)
    except Exception as e:
        print(str(e))
        return False


def getVariable(variable_name):
    try:
        return memcached.hash_client.get(variable_name)
    except Exception as e:
        print(str(e))
        return None


def clearVariable(variable_name):
    try:
        memcached.hash_client.delete(variable_name)
    except Exception as e:
        print(str(e))


number_to_add = 100
count = 0
added = 0
while True:
    # set number_to_add new variables
#    if not memcached.internal_scale:
    for i in range(count, count + number_to_add):
        if setVariable('foo_{}'.format(i), 'HelloWorld_{}'.format(i), 3600):
            added = added + 1
        if setVariable('foo_json_{}'.format(i), {'a': i, 'c': i}, 1800):
            added = added + 1
    count = count + number_to_add

    time.sleep(10)

    if os.path.isfile('add.node'):
        os.remove('add.node')
        memcached.add_node()
    if os.path.isfile('del.node'):
        os.remove('del.node')
        memcached.remove_node()

    read = 0
    # make sure we can get all variables back
#    if not memcached.internal_scale:
    for i in range(0, count):
        if getVariable('foo_{}'.format(i)):
            read = read + 1
        if getVariable('foo_json_{}'.format(i)):
            read = read + 1
    print('Read {} keys out of {}'.format(read, added))

