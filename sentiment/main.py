import os
import argparse
import ast
import torch
import redis
from transformers import DistilBertTokenizer

from model import SentimentClassifier

# error message written here to not repeat myself
dict_field_error_message = "Received input is either not a dict or it is missing required fields, which are:" \
                           "_id, inputs. Inputs should be mapped to a dictionary mapping keys to strings"


def prepare_input(tokenizer, max_length, sentence):
    tokens = tokenizer.tokenize(sentence)
    # data should being with [CLS], sentences should be separated (and end) with [SEP]
    tokens = ["[CLS]"] + tokens
    # truncate sequences that are too long
    tokens = tokens[:max_length - 1] + ["[SEP]"]

    # add padding it sequence is not long enough, so that sequences of different
    # length can fit in the same tensor
    tokens = tokens + ["[PAD]"] * (max_length - len(tokens))

    # tokens to their id in BERT vocab
    tokens_ids = tokenizer.convert_tokens_to_ids(tokens)
    tokens_ids = torch.tensor(tokens_ids)

    # attention mask: 1 for non PAD tokens, 0 otherwise
    attn_mask = (tokens_ids != 0).long()

    return tokens_ids, attn_mask


if __name__ == "__main__":
    for name in ["SENTIMENT_ANALYSIS_INPUT_QUEUE", "SENTIMENT_ANALYSIS_OUTPUT_QUEUE", "REDIS_HOST", "REDIS_PORT"]:
        assert name in os.environ, "%s environment variable is missing" % name

    input_queue = os.environ["SENTIMENT_ANALYSIS_INPUT_QUEUE"]
    output_queue = os.environ["SENTIMENT_ANALYSIS_OUTPUT_QUEUE"]

    parser = argparse.ArgumentParser()

    # checkpoint to use (from models/)
    parser.add_argument('--checkpoint', type=str, required=False)
    # max len of sequences
    parser.add_argument('--maxlen', type=int, required=False)
    args = parser.parse_args()
    args = args.__dict__
    print("Passed args:")
    print(args)

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print("Found device: %s" % device)

    print("loading model...")
    model = SentimentClassifier()
    model.to(device)  # Enable gpu support for the model

    checkpoint = torch.load(args["checkpoint"], map_location=device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    tokenizer = DistilBertTokenizer.from_pretrained("distilbert-base-uncased")
    print("model loaded")

    if not args["maxlen"]:
        args["maxlen"] = checkpoint["args"]["maxlen"]
        print("using maxlen from import checkpoint, new args:")
        print(args)

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
            assert "inputs" in received_input, dict_field_error_message
            assert isinstance(received_input["inputs"], dict), dict_field_error_message
            assert all(
                [isinstance(value, str) for value in received_input["inputs"].values()]), dict_field_error_message

            # prepare input data
            inputs = received_input["inputs"]
            inputs_names = inputs.keys()

            sentences_masks = [prepare_input(tokenizer, args["maxlen"],
                                             inputs[input_name]) for input_name in inputs_names]
            sentences = torch.cat([sent.unsqueeze(0) for (sent, _) in sentences_masks])
            sentences = sentences.to(device)
            masks = torch.cat([mask.unsqueeze(0) for (_, mask) in sentences_masks])
            masks = masks.to(device)

            logits = model.forward(sentences, masks)
            output = torch.sigmoid(logits)

            output = output.squeeze(1)
            output = output.tolist()

            print("sentiment computed, pushing to queue")
            del received_input["inputs"]
            # make it into a list so that no newlines are added when converting to string
            received_input["sentiments"] = {name: value for name, value in zip(inputs_names, output)}
            print(received_input)
            redis_connection.lpush(output_queue, str(received_input))

        except AssertionError as e:
            print(str(e))
        except (SyntaxError, ValueError):
            print("Data from sentiment analysis input not a valid python dict, discarding input:\n%s" % received_input)
        except Exception as e:
            print("Unexpected exception occurred:")
            print(str(e))
            print("Pushing None to queue")

            del received_input["inputs"]
            received_input["sentiments"] = str(None)
            print(received_input)
            redis_connection.lpush(output_queue, str(received_input))
