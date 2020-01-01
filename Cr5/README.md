Repository from: https://github.com/epfl-dlab/Cr5

I've simply added a main wich imports the model, connects
to redis and waits on a queue to process text.

Download the [embeddings](https://zenodo.org/record/2597441) (joint_28_en.text.gz) and put
them in src/model_28_txt/.