This collection of scripts, as the name might suggest, acts as some kind of broker
layer among crawlers, workers, the db, etc.

main.py: Keeps on waiting for data to be present in some output queues, and takes
care of cleaning it, adding it to the db, adding some other data to some input queues
for workers, etc.

ProcessCompany.py: contains what should take care of scraped companies info

ProcessJob.py: contains what should take care of scraped jobs info

ProcessReview.py: contains what should take care of scraped reviews info

language_prediction_model/: contains the pyfasttext model to detect languages.

data_collections/: each module contains a mongoengine document that models the data, job
offers, reviews of a compay, companies
    
