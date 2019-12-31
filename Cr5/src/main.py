import ast
import os
import redis

from cr5 import Cr5_Model

# error message written here to not repeat myself
dict_field_error_message = "Received input is either not a dict or it is missing required fields, which are:" \
                           "_id, text"

if __name__ == "__main__":
    for name in ["JOB_EMBEDDING_INPUT_QUEUE", "JOB_EMBEDDING_OUTPUT_QUEUE", "REDIS_HOST", "REDIS_PORT"]:
        assert name in os.environ, "%s environment variable is missing" % name

    input_queue = os.environ["JOB_EMBEDDING_INPUT_QUEUE"]
    output_queue = os.environ["JOB_EMBEDDING_OUTPUT_QUEUE"]

    print("loading model...")
    model = Cr5_Model('./model_28_txt/', 'joint_28')
    model.load_langs(['en'])
    print("model loaded")

    print("connecting to redis...")
    redis_connection = redis.Redis(host=os.environ["REDIS_HOST"], port=os.environ["REDIS_PORT"], charset="utf-8")
    print("connected to redis")

    print("starting work")
    while True:
        print("waiting for task")
        task = redis_connection.blpop(input_queue, 0)
        print("obtained task")

        try:
            received_input = task[1].decode("utf-8")
            received_input = ast.literal_eval(received_input)
            assert isinstance(received_input, dict), dict_field_error_message
            assert "id" in received_input, dict_field_error_message
            assert "text" in received_input, dict_field_error_message

            tokens = model.tokenize(received_input["text"])
            embedding = model.get_document_embedding(tokens, 'en')

            print("embedding computed, pushing to queue")
            del received_input["text"]
            # make it into a list so that no newlines are added when converting to string
            received_input["embedding"] = list(embedding)
            redis_connection.lpush(output_queue, str(received_input))

        except AssertionError as e:
            print(str(e))
        except (SyntaxError, ValueError):
            print("Data from job embedding input not a valid python dict, discarding input:\n%s" % received_input)
        except Exception as e:
            print("Unexpected exception occurred:")
            print(str(e))
            print("Pushing None to queue")

            del received_input["text"]
            received_input["embedding"] = str(None)
            print(received_input)
            redis_connection.lpush(output_queue, str(received_input))
