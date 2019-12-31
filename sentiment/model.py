import torch.nn as nn
from transformers import DistilBertModel


class SentimentClassifier(nn.Module):

    def __init__(self, freeze_bert=True, dropout=0.5):
        super(SentimentClassifier, self).__init__()
        # get pretrained distilbert
        self.bert_layer = DistilBertModel.from_pretrained('distilbert-base-uncased')

        # freeze bert parameters if requested
        if freeze_bert:
            for p in self.bert_layer.parameters():
                p.requires_grad = False

        # a couple of layers on top of the embedding
        self.pre_classifier = nn.Linear(768, 384)
        self.dropout = nn.Dropout(dropout)
        self.classifier = nn.Linear(384, 1)

    def forward(self, seq, attn_masks):
        """
        Inputs:
            -seq : Tensor of shape [batch size, sequence length] containing token ids of sequences
            -attn_masks : Tensor of shape [batch size, sequence length] containing attention masks to ignore PAD tokens
        """

        # simply get the first hidden state and process with a linear->relu->linear
        hidden_state = self.bert_layer(seq, attention_mask=attn_masks)[0]
        pooled_output = hidden_state[:, 0]
        pooled_output = self.pre_classifier(pooled_output)
        pooled_output = nn.ReLU()(pooled_output)
        pooled_output = self.dropout(pooled_output)
        logits = self.classifier(pooled_output)

        return logits
