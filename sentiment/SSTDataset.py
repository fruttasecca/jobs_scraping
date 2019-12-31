import pandas as pd
import torch
from torch.utils.data import Dataset
from transformers import DistilBertTokenizer


class SSTDataset(Dataset):

    def __init__(self, filename, maxlen):
        # Store the contents of the file in a pandas dataframe
        self.df = pd.read_csv(filename, delimiter="\t")

        # Initialize the BERT tokenizer
        self.tokenizer = DistilBertTokenizer.from_pretrained("distilbert-base-uncased")

        self.maxlen = maxlen

    def __len__(self):
        return len(self.df)

    def __getitem__(self, index):
        # Selecting the sentence and label at the specified index in the data frame
        sentence = self.df.loc[index, "sentence"]
        label = self.df.loc[index, "label"]

        # tokenize in a way that BERT expects
        tokens = self.tokenizer.tokenize(sentence)
        # data should being with [CLS], sentences should be separated (and end) with [SEP]
        tokens = ["[CLS]"] + tokens
        # truncate sequences that are too long
        tokens = tokens[:self.maxlen - 1] + ["[SEP]"]

        # add padding it sequence is not long enough, so that sequences of different
        # length can fit in the same tensor
        tokens = tokens + ["[PAD]"] * (self.maxlen - len(tokens))

        # tokens to their id in BERT vocab
        tokens_ids = self.tokenizer.convert_tokens_to_ids(tokens)
        tokens_ids = torch.tensor(tokens_ids)

        # attention mask: 1 for non PAD tokens, 0 otherwise
        attn_mask = (tokens_ids != 0).long()

        # no need for segment ids to signal which tokens belong to which sentence
        # of a pair since the input are not paired sentences
        return tokens_ids, attn_mask, label

