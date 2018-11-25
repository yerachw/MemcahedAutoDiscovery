import boto3
from pymemcache.client.hash import HashClient
import time
import json
from threading import Event, Thread
import os

#https://stackoverflow.com/questions/5730276/how-to-export-all-keys-and-values-from-memcached-with-python-memcache

class TimerThread(Thread):
    def __init__(self, function):
        Thread.__init__(self)
        self.function = function
        self.event = Event()

    def run(self):
        while not self.event.wait(60):
            self.function()



class AutodiscoveryClient(HashClient):

    def __init__(self, cluster_id):
        self.elasticache = boto3.client('elasticache', region_name='us-east-1')
        self.cluster_id = cluster_id
        self.servers = self.new_server_list()
        self.internal_scale = False
        super().__init__(self.servers, serializer=self.json_serializer, deserializer=self.json_deserializer, use_pooling=True)
        thread = TimerThread(self.check_cluster)
        thread.start()


    def new_server_list(self):
        new_servers = []
        response = self.elasticache.describe_cache_clusters(CacheClusterId=self.cluster_id, ShowCacheNodeInfo=True)
        nodes = response['CacheClusters'][0]['CacheNodes']
        for node in nodes:
            if 'Endpoint' in node:  # server may be coming up, no endpoint yet
                endpoint = (node['Endpoint']['Address'], node['Endpoint']['Port'])
                print(endpoint)
                new_servers.append(endpoint)
        return new_servers


    def check_cluster(self):
        print('Checking cluster')
        new_servers = self.new_server_list()

        try:
            for server, port in (set(new_servers) - set(self.servers)):
                print('Adding server {} on port'.format(server, port))
                self.add_server(server, port)
                if self.internal_scale:
                    for endpoint in self.servers:
                        ip, port = endpoint
                        print('Processing ' + ip)
                        command = 'memdump --servers={}:{} > keys.txt'.format(ip, port)
                        os.system(command)

                        not_found = []
                        with open('keys.txt', 'r') as f:
                            print('Opened key list')
                            for line in f.readlines():
                                key = line[:-1]
                                if not self.get(key):
                                    not_found.append(key)
                        os.remove('keys.txt')

                        print('Did not find {} keys'.format(len(not_found)))
                        client = HashClient([endpoint], serializer=self.json_serializer,
                                            deserializer=self.json_deserializer)
                        print('Created Hashclient for: ' + str(endpoint))
                        key_vals = client.get_many(not_found)
                        print('Found values for {} keys'.format(len(key_vals)))
                        response = self.set_many(key_vals)
                        print('Failed to set {} keys'.format(len(response)))

                    self.internal_scale = False

            for server, port in (set(self.servers) - set(new_servers)):
                print('Removing server {} on port'.format(server, port))
                self.remove_server(server, port)
        except Exception as e:
            print(str(e))

        self.servers = new_servers


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


cluster_id = 'scale-test'
memcached = AutodiscoveryClient(cluster_id)


def setVariable(variable_name, variable_value, expire_secs=0):
    try:
        memcached.set(key=variable_name, value=variable_value, expire=expire_secs)
    except Exception as e:
        print(str(e))


def getVariable(variable_name):
    try:
        return memcached.get(variable_name)
    except Exception as e:
        print(str(e))
        return None


def clearVariable(variable_name):
    try:
        memcached.delete(variable_name)
    except Exception as e:
        print(str(e))


number_to_add = 100
count = 0
while True:
    # set number_to_add new variables
    for i in range(count, count + number_to_add):
        setVariable('foo_{}'.format(i), 'HelloWorld')
        setVariable('foo_json_{}'.format(i), {'a': 'b', 'c': 'd'})

    time.sleep(10)

    if os.path.isfile('add.node'):
        os.remove('add.node')
        memcached.add_node()
    if os.path.isfile('del.node'):
        os.remove('del.node')
        memcached.remove_node()

    count = count + number_to_add
    read = 0
    # make sure we can get all variables back
    for i in range(1, count):
        if getVariable('foo_{}'.format(i)) and getVariable('foo_json_{}'.format(i)):
            read = read + 1
    print('Read {} vars out of {}'.format(read, count-1))

