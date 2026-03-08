from services.stats import XrayStatsService

service = XrayStatsService(
    panel_url='http://72.56.118.169:2053',
    username='xCwgwlzm8x',
    password='JOcBS87g30',
    web_base_path='YFBFh5UWZXQ7YxG6lt'
)

print("Testing connection...")
if service.test_connection():
    print("SUCCESS: Connected to 3x-ui panel!")
    
    clients = service.get_all_clients()
    print(f"Found {len(clients)} clients:")
    for c in clients[:5]:
        print(f"  - {c}")
else:
    print("ERROR: Connection failed")
