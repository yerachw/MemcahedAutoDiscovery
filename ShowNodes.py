import boto3


client = boto3.client('elasticache', region_name='us-east-1')
cluster_id = 'yourcopy-m-staging'

response = client.describe_cache_clusters(CacheClusterId=cluster_id, ShowCacheNodeInfo=True)
nodes = response['CacheClusters'][0]['CacheNodes']
print(nodes)

