import boto3
import time

client = boto3.client('elasticache', region_name='us-east-1')
cluster_id = 'scale-test'
bAddServer = True
while True:
    response = client.describe_cache_clusters(CacheClusterId=cluster_id, ShowCacheNodeInfo=True)
    count = response['CacheClusters'][0]['NumCacheNodes']
    if bAddServer:
        print('Adding server')
        response = client.modify_cache_cluster(CacheClusterId=cluster_id, NumCacheNodes=count+1, ApplyImmediately=True)
    else:
        print('Removing server')
        nodes = response['CacheClusters'][0]['CacheNodes']
        id_to_remove = nodes[count - 1]['CacheNodeId']
        response = client.modify_cache_cluster(CacheClusterId=cluster_id, NumCacheNodes=count - 1,
                                               CacheNodeIdsToRemove=[id_to_remove], ApplyImmediately=True)
    print(response)

    bAddServer = not bAddServer

    time.sleep(720)

# response = client.describe_cache_clusters(CacheClusterId='yourcopy-m-staging', ShowCacheNodeInfo=True)
# print(response)
#
# count = response['CacheClusters'][0]['NumCacheNodes']
# nodes = response['CacheClusters'][0]['CacheNodes']

# THIS CODE ADDS A NODE
#response = client.modify_cache_cluster(CacheClusterId='yourcopy-m', NumCacheNodes=count+1, ApplyImmediately=True)

# THIS DELETES A NODE
#id_to_remove = nodes[count-1]['CacheNodeId']
#response = client.modify_cache_cluster(CacheClusterId='yourcopy-m', NumCacheNodes=count-1, CacheNodeIdsToRemove=[id_to_remove], ApplyImmediately=True)

# print(response)