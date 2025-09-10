from google.cloud import storage

client = storage.Client()
bucket = client.bucket("line-bot-images-123456")  # 換成你的 bucket 名稱
blob = bucket.blob("test/hello.txt")
blob.upload_from_string("hello gcs")
print("uploaded, public url (if public):", blob.public_url)
