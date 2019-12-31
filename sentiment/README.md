Expanded code starting from
https://github.com/kabirahuja2431/FineTuneBERT

data/: training data
models/: contains saved models


this directory:

SSTDataset.py: Custom torch dataset, only used for training.\
model.py: The network architecture (distilbert -> linear -> relu -> linear)\
train.py: Expects a gpu, allows you to train/save a model and to resume training. Getting to an evaluation
around 0.89-0.90 is pretty straightforward.\
main.py: Imports a model, connect to redis and waits on a queue to process the
sentiment score of text.

