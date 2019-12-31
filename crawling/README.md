Scrapy spiders that are in a loop so that they can
wait on tasks from redis queues, start a crawl, then wait again
after the crawl is done.

crawling/
- country_to_id.json: maps country names to their glassdoor code
- items.py: Currently contains only the code to import country_to_id.json, allows
for future extensions using scrapy items.
- main.py: starts the loop of spiders waiting on (job/company) input queues, receiving
input in the form of <job>|||sep|||<location> or <company|||sep|||<location> will start
a crawl, push data in a redis output queue, then wait again on input queues.

    spiders/   
        Here you find all the defined spiders, you can pretty much simply add a spider in
        here and update the spiders list in main.py to have your custom spiders send scraped
        data to the redis output queue.
    
    