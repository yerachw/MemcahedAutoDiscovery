import boto3
from pymemcache.client.hash import HashClient
import time
import json
from threading import Event, Thread

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
        super().__init__(self.servers, serializer=self.json_serializer, deserializer=self.json_deserializer, use_pooling=True)
        thread = TimerThread(self.check_cluster)
        thread.start()


    def new_server_list(self):
        new_servers = []
        response = self.elasticache .describe_cache_clusters(CacheClusterId=self.cluster_id, ShowCacheNodeInfo=True)
        nodes = response['CacheClusters'][0]['CacheNodes']
        for node in nodes:
            if 'Endpoint' in node:  # server may be coming up, no endpoint yet
                endpoint = (node['Endpoint']['Address'], node['Endpoint']['Port'])
                new_servers.append(endpoint)
        return new_servers


    def check_cluster(self):
        print('Checking cluster')
        new_servers = self.new_server_list()

        for server, port in (set(new_servers) - set(self.servers)):
            print('Adding server {} on port'.format(server, port))
            self.add_server(server, port)

        for server, port in (set(self.servers) - set(new_servers)):
            print('Removing server {} on port'.format(server, port))
            self.remove_server(server, port)

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


cluster_id = 'scale-test'
memcached = AutodiscoveryClient(cluster_id)


def setVariable(variable_name, variable_value, expire_secs=0):
    memcached.set(key=variable_name, value=variable_value, expire=expire_secs)


def getVariable(variable_name):
    return memcached.get(variable_name)


def clearVariable(variable_name):
    memcached.delete(variable_name)

number_to_add = 100
count = 0
while True:
    # set number_to_add new variables
    for i in range(count, count + number_to_add):
        setVariable('foo_{}'.format(i+count), 'HelloWorld')
        setVariable('foo_json_{}'.format(i+count), {'a': 'b', 'c': 'd'})

    time.sleep(10)

    count = count + number_to_add
    read = 0
    # make sure we can get all variables back
    for i in range(1, count):
        getVariable('foo_{}'.format(i+count))
        getVariable('foo_json_{}'.format(i+count))
        read = read + 1
    print('Read {} vars out of {}'.format(read, count))

