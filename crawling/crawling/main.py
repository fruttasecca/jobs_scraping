import os
import redis
from twisted.internet import reactor
from scrapy.crawler import CrawlerRunner
from scrapy.settings import Settings
from spiders import GlassdoorCompanies, GlassdoorJobs
from scrapy.utils.log import configure_logging


def set_settings(settings):
    settings.set("BOT_NAME", "ebin")
    settings.set("USER_AGENT",
                 "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) snap Chromium/78.0.3904.108 Chrome/78.0.3904.108 Safari/537.36")
    settings.set("ROBOTSTXT_OBEY", False)
    settings.set("CONCURRENT_REQUESTS_PER_DOMAIN", 1)
    settings.set("CONCURRENT_REQUESTS_PER_IP", 1)
    settings.set("DEFAULT_REQUEST_HEADERS", {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.8,zh-CN;q=0.6,zh;q=0.4',
    })
    settings.set("HTTPCACHE_ENABLED", False)
    settings.set("FEED_EXPORT_ENCODING", "utf-8")
    settings.set("LOG_FILE", "log.txt")
    settings.set("LOGENABLED", True)
    settings.set("STATS_ENABLED", True)
    settings.set("AUTOTHROTTLE_TARGET_CONCURRENCY", 1.0)
    settings.set('ITEM_PIPELINES', {'__main__.SendToRedis': 1})


class SendToRedis(object):
    """ A custom pipeline that stores scrape results in 'results'"""

    def process_item(self, item, spider):
        redis_connection.lpush(crawler_output_queue, str(item))
        return item


def check_for_task():
    found_correct_input = False

    while not found_correct_input:
        print("waiting for a task")
        task = redis_connection.blpop([company_input_queue, job_input_queue], 0)
        task0 = task[0].decode("utf-8")
        task1 = task[1].decode("utf-8")
        if task1.count("|||sep|||") != 1:
            print("Discarding %s, not properly formatted (missing or more than 1 internal-separator |||sep|||)" % str(
                task))
        else:
            keyword, location = task1.split("|||sep|||")
            if task0 == job_input_queue:
                run_spiders(JOB_SPIDERS, settings, {"job": keyword, "country": location})
            elif task0 == company_input_queue:
                run_spiders(COMPANY_SPIDERS, settings, {"company": keyword, "country": location})
            found_correct_input = True


def run_spiders(spiders_to_run, settings, kwargs):
    """
    Runs a list of spiders with some given arguments and settings.
    Args:
        spiders_to_run:
        settings:
        kwargs:

    Returns:

    """
    print("starting crawl task with arguments %s" % str(kwargs))
    runner = CrawlerRunner(settings)
    for spider in spiders_to_run:
        runner.crawl(spider, stop_after_crawl=False, **kwargs)
    # what to do once crawling is over
    d = runner.join()
    d.addBoth(lambda _: check_for_task())


if __name__ == "__main__":
    for name in ["CRAWLER_JOB_INPUT_QUEUE", "CRAWLER_COMPANY_INPUT_QUEUE", "CRAWLER_OUTPUT_QUEUE",
                 "REDIS_HOST", "REDIS_PORT"]:
        assert name in os.environ, "%s environment variable is missing" % name

    job_input_queue = os.environ["CRAWLER_JOB_INPUT_QUEUE"]
    company_input_queue = os.environ["CRAWLER_COMPANY_INPUT_QUEUE"]
    crawler_output_queue = os.environ["CRAWLER_OUTPUT_QUEUE"]

    # crawlers to use based on task
    JOB_SPIDERS = [GlassdoorJobs.GlassdoorJobs]
    COMPANY_SPIDERS = [GlassdoorCompanies.GlassdoorCompanies]

    print("connecting to redis...")
    redis_connection = redis.Redis(host=os.environ["REDIS_HOST"], port=os.environ["REDIS_PORT"], charset="utf-8")
    print("connected to redis")

    settings = Settings()
    set_settings(settings)

    # needed for logging
    configure_logging()
    check_for_task()
    print("starting reactor")
    reactor.run()
