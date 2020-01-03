# jobs_scraping
Scrape, organize and present job offers and companies. Dockerized and good to go with a 
simple ``docker-compose up``.

## What & Why
This is a personal project that I undertook to practise some tools, such as **Redis**, **MongoDB**,
**Scrapy**, **Django** and **Docker**, and to try out some machine learning stuff like **document embeddings** and models such as **Bert**, **Distilbert** using the **transformers** library.  
In its current state it allows to scrape jobs, companies and companies reviews, starting from some search
keywords. Data is then stored in MongoDB and can be later explored through the browser at ``127.0.0.1:8000``.  
A Distilbert model fine tuned on sentiment analysis (``SST-2 dataset``) is used to score the sentiment of each
review related to a company, while a document embedding model (``josifoski-wsdm2019-cr5``) transforms
each job offer into a numerical array that allows to search for similar jobs by sorting 
on the cosine similarity. 

### Views

 When searching for jobs or companies we might be returned some data. Both jobs and companies
 are compared through some metrics with other results in the search, to allow for more 
 insight on what life in the company could be and to allow sorting based on 
 some metrics, such as work life balance, career opportunities, etc. By clicking on 
 their name we will be brought to a detailed page for a job offer or a company.  
 When searching for job offers a word cloud of said offers is provided to give a general idea 
 about buzzwords and the like.  
 The search bar allows you to also start a crawl for a given job/company at a given location, after
 eventually starting in the background (given the current task and input queues of the crawler) relatd
 data will begin to populate the database.  
 Note that when searching in the db, specifying the location will require (a case insensitive) match
 with a city, state or country. These fields might often not be there but present in the job
 description text (even if said data was found through a crawl with a given 
 specific location), so it might better to add the location to the searched keywords instead
 of specifying it in the location form input.

![Alt text](images/index.png?raw=true "A look at the index of the client")  
---
 
  A job offer page, simply put, contains the job description as it was scraped. 
  Some more details, such as location, employer, etc. might be present, depending on their availability.
  
 ![Alt text](images/job_details.png?raw=true "A look at a job offer page")  
---

 A company page offers a general outlook about the company, its job offers and the reviews it has received.  
 Each company might be characterized by more or less data, depending on what is present in the db.  
 Among general info such as headquarters, revenue, competitors etc., one interesting feature 
 is the ability to visualize, for some selected metrics (such as work life balance, 
 career opportunities, benefits, etc.), a comparison between this company, the 
 mean of all companies belonging to the same industry, and the mean of all companies in the db.
 
 ![Alt text](images/company_details.png?raw=true "A look at a company page")  
 ---
 
### Usage & Extension
The **project is easily extensible** and further models can be plugged in to 
obtain different estimations, metrics, classifications etc. The same can be said for 
the crawling side, scrapy spiders can be written for different websites and plugged into the 
project to have data coming from more sources.  
**When implementing a new spider** you just have to make sure that the returned data has a "type" field
containing a type (an arbitrary string) that will be matched by the ``broker`` module that 
takes care of wrangling data around redis, the db, etc. If you are interested in 
customizing what the broker does to incoming data, that can be easily done without disrupting 
other functionalities.  
**When implementing new modules** (e.g. a new machine learning model for some task), 
you will have to dockerize it and add a service related to it in the docker-compose file 
contained in the docker directory. Moreover, it will likely send/poll 
data to/from redis, so you might have to (or can) add some custom 
redis queues or other data structures in the environment variables and in the broker module
, which should only take a few lines of code.  
If some choices seem off, it might be that they were completely arbitrary because I wanted to try out
something in particular among the libraries/tools I've used.

>Tip: When crawling, it might be better to be using a vpn or a proxy to have an ip of an english speaking country. Some websites, such as Glassdoor, might only return reviews (or other data) that are in your (detected) language, resulting in some missed data. In my experience, this is especially true for Glassdoor reviews.  

>Tip: Given your resources and/or your internet connection you may want to scale up the number of replicas for a specific 
>service.

## How
The project consists of a number of modules with different concerns. Each module is dockerized 
and the overall architecture tries to be as extensible as possible.  The whole thing can be 
started with a ``docker-compose up'`` or a ``docker stack deploy --compose-file=docker-compose.yml name``. 
Along redis and mongoDB, the modules are:
 - **crawling**: a loop blocked (**BLPOP**, blocking pop) on two redis queues (job or company search terms) waiting for input. Once input is received, crawling and scraping begins on the present spiders and data is put into another redis queue.
 - **broker**: looping on inputs queues waiting for inputs, takes care of wrangling and cleaning data, pushing to db or to other redis queues to provide tasks for the text embedding and sentiment analysis modules.
 - **text_embedding**: waits for input on a redis queue to compute document embeddings of job offers, which will then be pushed to another redis queue (consumed by the broker module).
 - **sentiment_analysis**: waits for input on a redis queue to compute a sentiment score [0,1] for incoming reviews, results are then pushed to another redis queue 
 (consumed by the broker module).  
 While this could potentially
 use the GPU, docker-compose is currently not supported, 
 refer to this [issue](https://github.com/docker/compose/issues/6691) for updates.
 The sentiment score is computed by a distilbert model fine tuned on the SST-2 dataset. 
  While the model was trained on a gpu, I've found the inference time on cpu to be quite reasonable.
 - **client**: a django project which gets data from db and presents it through html pages, 
 allows for searching jobs or companies, getting detailed information about them and 
 issuing new scraping tasks to the crawling module by pushing to a redis queue.
Each module has its own directory containing a README with more details about the module 
implementation and usage.

![Alt text](images/architecture_diagram.png?raw=true "Architecture of the project")

---
### Resources 
- [scrapy](https://scrapy.org/)
- [nltk](https://www.nltk.org/)
- [Document Embedding (Cr5)](https://github.com/epfl-dlab/Cr5)
- [pytorch](https://pytorch.org/)
- [transformers library](https://github.com/huggingface/transformers)
- [Bert](https://arxiv.org/abs/1810.04805), [DistilBert](https://arxiv.org/abs/1910.01108)
- [SST-2](https://paperswithcode.com/sota/sentiment-analysis-on-sst-2-binary)
- [django](https://www.djangoproject.com/)

