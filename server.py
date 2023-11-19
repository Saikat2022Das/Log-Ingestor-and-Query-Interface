import json
from threading import Thread
from fastapi import FastAPI, Query
from dateutil import parser
from kafka import KafkaProducer, KafkaConsumer
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from datetime import datetime

app = FastAPI()

# Enable CORS for all origins
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017")
collection = client["dyte"]["logs"]
collection.create_index([('message', 'text')])

# Kafka configuration
kafka_bootstrap_servers, kafka_topic = 'localhost:9092', 'dyte-logs'
producer = KafkaProducer(bootstrap_servers=kafka_bootstrap_servers, value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'))
consumer = KafkaConsumer(kafka_topic, bootstrap_servers=kafka_bootstrap_servers, value_deserializer=lambda x: json.loads(x.decode('utf-8')))

def kafka_producer_worker(data):
    producer.send(kafka_topic, value=data)

def kafka_consumer_worker():
    for message in consumer:
        try:
            data = message.value
            data["tObj"], data['pRID'] = parser.parse(data["timestamp"]), data['metadata']['parentResourceId']
            collection.insert_one(data)
            print("Successful")
        except Exception as e:
            print(f"Error processing Kafka message: {str(e)}")

# Start Kafka Consumer in a separate thread
Thread(target=kafka_consumer_worker).start()

@app.post("/")
async def handle_logs(data: dict):
    Thread(target=kafka_producer_worker, args=(data,)).start()
    return {"message": "Data Recieved"}

@app.get("/logs/")
async def filtered_logs(level: str = Query(None), resourceId: str = Query(None),
                        start_timestamp: datetime = Query(None),
                        end_timestamp: datetime = Query(None),
                        traceId: str = Query(None),
                        spanId: str = Query(None),
                        commit: str = Query(None),
                        pRID: str = Query(None),
                        search_text: str = Query(None)):
    filters = {k: v for k, v in locals().items() if v is not None and k not in ["self", "filters"]}
    if start_timestamp:
        filters["tObj"] = {"$gte": start_timestamp, "$lte": end_timestamp}
        del filters['start_timestamp'], filters['end_timestamp']
    if search_text:
        filters["$text"] = {"$search": search_text}
        del filters['search_text']
    
    result = list(collection.find(filters, {'_id': False, 'pRID': False, 'tObj': False}))
    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=3000)
