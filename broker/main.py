import ast
import os
from pyfasttext import FastText
import redis
from mongoengine import *

from data_collections.Company import Company
from data_collections.Job import Job
from data_collections.Review import Review
from ProcessJob import process_job, process_job_embedding
from ProcessReview import process_review, process_review_sentiment
from ProcessCompany import process_company_general_info, process_company_aggregate_reviews_info

if __name__ == "__main__":
    for name in ["JOB_EMBEDDING_OUTPUT_QUEUE", "CRAWLER_OUTPUT_QUEUE",
                 "SENTIMENT_ANALYSIS_OUTPUT_QUEUE", "CRAWLER_COMPANY_INPUT_QUEUE",
                 "JOB_EMBEDDING_INPUT_QUEUE", "SENTIMENT_ANALYSIS_INPUT_QUEUE", "MONGODB_NAME",
                 "REDIS_HOST", "REDIS_PORT", "MONGODB_HOST", "MONGODB_PORT"]:
        assert name in os.environ, "%s environment variable is missing." % name

    print("import language prediction model")
    language_model = FastText('language_prediction_model/lid.176.ftz')
    print("imported language prediction model")

    print("connecting to redis...")
    redis_c = redis.Redis(host=os.environ["REDIS_HOST"], port=os.environ["REDIS_PORT"], charset="utf-8")
    print("connected to redis")

    print("creating connection to mongodb")
    connect(os.environ["MONGODB_NAME"], host=os.environ["MONGODB_HOST"], port=int(os.environ["MONGODB_PORT"]))
    print("connection to mongodb created")

    # set up redis queues to wait on for tasks
    redis_queues = []
    for name in ["JOB_EMBEDDING_OUTPUT_QUEUE", "CRAWLER_OUTPUT_QUEUE",
                 "SENTIMENT_ANALYSIS_OUTPUT_QUEUE"]:
        redis_queues.append(os.environ[name])

    print("starting to work")
    while True:
        print("waiting for task")
        task = redis_c.blpop(redis_queues, 0)
        received_queue = task[0].decode("utf-8")
        received_input = task[1].decode("utf-8")
        print("received task from %s" % received_queue)

        try:
            received_input = ast.literal_eval(received_input)

            if received_queue == os.environ["CRAWLER_OUTPUT_QUEUE"]:
                assert "type" in received_input, "Data from %s is a valid dictionary but is missing key 'type'" \
                                                 % received_queue
                data_type = received_input["type"]
                print("crawler output type %s" % data_type)

                if data_type == "job":
                    process_job(redis_c, os.environ["CRAWLER_COMPANY_INPUT_QUEUE"],
                                os.environ["JOB_EMBEDDING_INPUT_QUEUE"], language_model, received_input)
                elif data_type == "review":
                    process_review(redis_c, os.environ["SENTIMENT_ANALYSIS_INPUT_QUEUE"], language_model,
                                   received_input)
                elif data_type == "company_general_info":
                    process_company_general_info(received_input)
                elif data_type == "company_aggregate_reviews_info":
                    process_company_aggregate_reviews_info(received_input)

            elif received_queue == os.environ["JOB_EMBEDDING_OUTPUT_QUEUE"]:
                process_job_embedding(received_input)
            elif received_queue == os.environ["SENTIMENT_ANALYSIS_OUTPUT_QUEUE"]:
                process_review_sentiment(received_input)
        except AssertionError as e:
            print(str(e))
        except SyntaxError:
            print("Data from %s not a valid python dict, discarding:\n %s" % (received_queue, received_input))
