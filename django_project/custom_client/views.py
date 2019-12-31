import os
from django.shortcuts import render
from django.http import HttpResponse
from mongoengine import *
from modules.data_collections.Job import Job
from modules.data_collections.Company import Company
from modules.data_collections.Review import Review
import nltk
from nltk.corpus import stopwords
import collections
import numpy as np
from numpy import dot
from numpy.linalg import norm
from sklearn.preprocessing import normalize
import redis
import datetime

for name in ["CRAWLER_JOB_INPUT_QUEUE", "CRAWLER_COMPANY_INPUT_QUEUE",
             "REDIS_HOST", "REDIS_PORT", "MONGODB_NAME", "MONGODB_HOST", "MONGODB_PORT"]:
    assert name in os.environ, "%s environment variable is missing." % name

mongo_db_name = os.environ["MONGODB_NAME"]
connect(os.environ["MONGODB_NAME"], host=os.environ["MONGODB_HOST"], port=int(os.environ["MONGODB_PORT"]))

# to remove stopwords when comparing jobs
nltk.download('stopwords')
__stopwords = set(stopwords.words("english"))

print("connecting to redis")
redis_c = redis.Redis(host=os.environ["REDIS_HOST"], port=os.environ["REDIS_PORT"], db=0)
print("connected to redis")


def job_details(request, id):
    """
    Returns a page containing details about a job offer, given the job mongodb id.
    Args:
        request:
        id:

    Returns:

    """
    jobs = Job.objects(id=id)
    if not jobs:
        return HttpResponse("Something went wrong :(")

    job = jobs[0]._data
    job = {k: v for (k, v) in job.items() if v is not None}
    context = dict()
    context["job"] = job

    if "date_last_modify" in job:
        job["date_last_modify"] = job["date_last_modify"].date

    # no need to have the actual embedding, just to have information about its existence in the template
    if "embedding" in job and len(job["embedding"]) == 300:
        job["embedding"] = True
    else:
        job.pop("embedding", None)

    # add company info if possible
    if "employer_glassdoor_id" in job:
        company = Company.objects(glassdoor_id=job["employer_glassdoor_id"])
        if company:
            company = company[0]._data
            company = {k: v for (k, v) in company.items() if v is not None}
            context["company"] = company
    return render(request, "custom_client/job_details.html", context)


def company_details(request, id):
    """
    Returns a page containing details about a company, given the company glassdoor id.
    Args:
        request:
        id:

    Returns:

    """
    companies = Company.objects(glassdoor_id=id)
    if not companies:
        return HttpResponse("Something went wrong :(")

    # company general info
    company = companies[0]._data
    context = dict()
    context["company"] = company

    # reviews, word cloud from reviews and sentiment of reviews
    reviews = Review.objects(employer_glassdoor_id=company["glassdoor_id"])
    reviews = [review._data for review in reviews]
    context["reviews"] = reviews

    reviews_tags = get_reviews_top_tags(reviews, 5)
    if len(reviews_tags) > 0:
        context["reviews_tags"] = reviews_tags

    reviews_words = get_reviews_normalized_words_count(reviews, 255, 30)
    if len(reviews_words) > 0:
        context["frequent_words"] = reviews_words

    sentiments = [review["sentiment_score"] for review in reviews if review.get("sentiment_score", None)]
    if len(sentiments) > 0:
        sentiments = sum(sentiments) / len(sentiments)
        context["reviews_sentiment_score"] = sentiments

    # job offers from said company
    jobs = Job.objects(employer_glassdoor_id=company["glassdoor_id"])
    jobs = [job._data for job in jobs]
    context["jobs"] = jobs

    # get average over all companies of some metrics
    group_dict = dict()
    group_dict["_id"] = "averages"
    avgs_fields = ["overall_rating", "culture_and_values", "career_opportunities", "work_life_balance",
                   "senior_management", "ceo_rating", "biz_outlook", "recommend", "comp_and_benefits"]
    avgs_fields = filter(lambda x: isinstance(company.get(x, None), float), avgs_fields)
    for field in avgs_fields:
        group_dict[field] = {"$avg": "$%s" % field}

    pipeline = [
        {"$group": group_dict}

    ]
    all_companies_avgs = list(Company.objects.aggregate(*pipeline))[0]
    context["all_companies_avgs"] = all_companies_avgs

    # get average over companies in the same industry of som metrics
    industry = company.get("industry", None)
    if industry:
        pipeline = [
            {"$match": {"industry": industry}},
            {"$group": group_dict}
        ]
        same_industry_companies_avgs = list(Company.objects.aggregate(*pipeline))[0]
        context["same_industry_companies_avgs"] = same_industry_companies_avgs

    return render(request, "custom_client/company_details.html", context)


__search_employer_fields = ["overall_rating", "culture_and_values", "career_opportunities", "work_life_balance"]


def search(request):
    """
    Returns a page with the search results that the user has queried for (jobs or companies).
    Args:
        request:

    Returns:

    """
    context = dict()

    # a request to get jobs similar the one related to this id, by using the job text embeddings
    if "job_id" in request.POST:
        jobs = get_similar_jobs_by_embedding(request.POST["job_id"])
        return render_jobs(request, context, jobs)
    # a search request with keyword and/or location
    elif "keywords" in request.POST:
        kw = request.POST["keywords"]
        context["keywords_value"] = kw

        loc = request.POST.get("location", None)
        if loc:
            context["location_value"] = loc

        search_type = request.POST.get("search_type", None)
        if search_type == "company":
            context["searched_company"] = True

        crawl = request.POST.get("start_crawl", "false")
        if crawl == "true":
            context["crawl_value"] = crawl

        # check that we receive correct stuff
        incorrect_input = any(not isinstance(item, str) for item in [kw, loc, search_type, crawl])
        incorrect_input = incorrect_input or search_type not in ["job", "company"]
        incorrect_input = incorrect_input or crawl not in ["true", "false"]

        if incorrect_input:
            return HttpResponse("Something went wrong :(")

        if search_type == "job":
            return render_jobs_search(request, context, os.environ["CRAWLER_JOB_INPUT_QUEUE"], kw, loc)

        elif search_type == "company":
            return render_company_search(request, context, os.environ["CRAWLER_COMPANY_INPUT_QUEUE"], kw, loc)

    return render_jobs(request, context, [])


def render_company_search(request, context, crawler_company_input_queue, keyword, location):
    """
    Given search keyword and location find related companies in the database and render the page, if crawl_value
    is true in the context dictionary this function also starts a crawl for given keyword and location.

    Args:
        request: Request that started this search.
        context: Context of data for the template to render.
        crawler_company_input_queue: Redis input queue of crawlers for company related tasks.
        keyword: Keyword of the search.
        location: Location of the search.

    Returns: Render of the template containing the search results.

    """
    if keyword != "" and location != "":
        keyword = " ".join([keyword, location])
    elif location != "":
        keyword = location
    if keyword != "":
        companies = Company.objects().search_text(keyword, language="en").order_by('$text_score')
    else:
        companies = Company.objects().order_by('-date_last_modify')[:100]

    # avg values for companies in the search result
    group_dict = dict()
    group_dict["_id"] = "averages"
    for field in ["overall_rating", "culture_and_values", "career_opportunities", "work_life_balance"]:
        group_dict[field] = {"$avg": "$%s" % field}
    pipeline = [
        {"$group": group_dict}

    ]
    companies_avgs = list(companies.aggregate(*pipeline))

    companies = [company._data for company in companies]

    for company in companies:

        # some formatting
        for key in company:
            if company[key] is None:
                company[key] = "-"

        # remove time from day
        if "date_last_modify" in company and isinstance(company["date_last_modify"], datetime.datetime):
            company["date_last_modify"] = company["date_last_modify"].date

        for field in __search_employer_fields:
            if field in company and isinstance(company[field], float):
                company[field + "_difference"] = round(company[field] - companies_avgs[0][field], 1)

    context["companies"] = companies
    if context.get("crawl_value", False):
        redis_c.lpush(crawler_company_input_queue, "%s|||sep|||%s" % (keyword, location))
    return render(request, "custom_client/index.html", context)


def render_jobs_search(request, context, crawler_job_input_queue, keyword, location):
    """
    Given search keyword and location find related jobs in the database and render the page, if crawl_value
    is true in the context dictionary this function also starts a crawl for given keyword and location.

    Args:
        request: Request that started this search.
        context: Context of data for the template to render.
        crawler_job_input_queue: Redis input queue of crawlers for job related tasks.
        keyword: Keyword of the search.
        location: Location of the search.

    Returns: Render of the template containing the search results.

    """
    if location != "":
        loc_variations = [location, location.lower(), location.upper(), location.capitalize()]
        query = Q(city=location)
        for loc in loc_variations:
            query = query | Q(city=loc) | Q(country=loc) | Q(state=loc)

        if keyword != "":
            jobs = Job.objects(query).search_text(keyword, language="en").order_by('$text_score')
        else:
            jobs = Job.objects(query).order_by("-date_last_modify")
    else:
        if keyword != "":
            jobs = Job.objects().search_text(keyword, language="en").order_by('$text_score')
        else:
            jobs = Job.objects().order_by("-date_last_modify")[:100]

    if context.get("crawl_value", False):
        redis_c.lpush(crawler_job_input_queue, "%s|||sep|||%s" % (keyword, location))
    jobs = [job._data for job in jobs]

    return render_jobs(request, context, jobs)


def render_jobs(request, context, jobs):
    """
    Takes care of rendering the template with the correct information given some jobs documents.
    Args:
        request:
        context:
        jobs:

    Returns:

    """

    # get ids of employers for the given job offerings
    employer_glassdoor_ids = list(
        set([job["employer_glassdoor_id"] for job in jobs if "employer_glassdoor_id" in job]))

    # get frequent words of job offers for a word cloud
    frequent_words = get_job_normalized_words_count(jobs, 255, 30)

    # get companies related to the found jobs and their average metrics
    jobs_companies = get_jobs_companies(employer_glassdoor_ids)
    jobs_companies_avgs = get_jobs_companies_averages(employer_glassdoor_ids)

    # for each job add company ratings fields if possible
    for job in jobs:

        # some minor cleaning
        for key in job:
            if job[key] is None:
                job[key] = "-"

        # format date
        if "date_last_modify" in job and isinstance(job["date_last_modify"], datetime.datetime):
            job["date_last_modify"] = job["date_last_modify"].date

        # add company(ies) info
        if "employer_glassdoor_id" in job:
            company = list(filter(lambda x: x["glassdoor_id"] == job["employer_glassdoor_id"], jobs_companies))
            if company:
                company = company[0]
            for field in __search_employer_fields:
                if field in company and isinstance(company[field], float):
                    job["emp_" + field] = company[field]
                    job["emp_" + field + "_difference"] = round(company[field] - jobs_companies_avgs[0][field],
                                                                1)
                else:
                    job["emp_" + field] = "-"
        else:
            for field in __search_employer_fields:
                job["emp_" + field] = "-"
        context["jobs"] = jobs
        context["frequent_words"] = frequent_words

    return render(request, "custom_client/index.html", context)


###############################
# utility stuff
###############################

def get_jobs_companies(companies_ids):
    """
    Get companies related to given ids.
    Args:
        companies_ids:

    Returns:

    """
    pipeline = [
        {
            "$match":
                {
                    "glassdoor_id": {"$in": companies_ids}
                }
        },

    ]
    return list(Company.objects.aggregate(*pipeline))


def get_jobs_companies_averages(companies_ids):
    """
    Get average metrics of companies related to given ids.
    Args:
        companies_ids:

    Returns:

    """
    group_dict = dict()
    group_dict["_id"] = "averages"
    for field in ["overall_rating", "culture_and_values", "career_opportunities", "work_life_balance"]:
        group_dict[field] = {"$avg": "$%s" % field}
    {"$group": group_dict}
    pipeline = [
        {
            "$match":
                {
                    "glassdoor_id": {"$in": companies_ids}
                }
        },
        {"$group": group_dict}
    ]
    return list(Company.objects.aggregate(*pipeline))


def normalized_word_counts(data, factor, top_k):
    """

    Args:
        data:
        factor: Factor by which the normalized count of each word should be multiplied.
        top_k: Keep only the top-k words with highest count.

    Returns:

    """
    frequent_words = collections.Counter(
        [word.lower() for word in data if word.lower() not in __stopwords and len(word) > 1]).most_common(top_k)

    # normalize and rescale
    values = normalize([[w[1] for w in frequent_words]], norm='l2')
    frequent_words = [(word[0], value * factor) for word, value in zip(frequent_words, values[0])]

    return frequent_words


def get_job_normalized_words_count(jobs, factor, top_k):
    """
    Normalize the count of each word w.r.t to the others and multiply by a factor the result (needed
    to have a more robust/predictable drawing of the word cloud.
    Args:
        jobs:
        factor: Factor by which the normalized count of each word should be multiplied.
        top_k: Keep only the top-k words with highest count.

    Returns:
    """
    if not jobs:
        return []

    data = []
    for job in jobs:
        text = job.get("description_text", None)
        if text:
            data.extend(text.split())

    return normalized_word_counts(data, factor, top_k)


def get_reviews_normalized_words_count(reviews, factor, top_k):
    """
    Normalize the count of each word w.r.t to the others and multiply by a factor the result (needed
    to have a more robust/predictable drawing of the word cloud.
    Args:
        reviews:
        factor: Factor by which the normalized count of each word should be multiplied.
        top_k: Keep only the top-k words with highest count.

    Returns:
    """
    if not reviews:
        return []

    data = []
    for review in reviews:
        for name in ["pros", "cons", "advice_to_management"]:
            if name in review and review[name] is not None:
                data.extend(review[name].split())

    return normalized_word_counts(data, factor, top_k)


def get_reviews_top_tags(reviews, top_k):
    """
    Get the most common tags of the reviews of a company.

    Args:
        reviews: List of reviews as dicts.
        top_k: Keep only the top_k most common

    Returns: List of the top_k most common tags.

    """
    tags = [tag for review in reviews for tag in review.get("recommendation_tags", []) if tag is not None]
    tags = collections.Counter(tags).most_common(top_k)

    return tags


def get_similar_jobs_by_embedding(job_id):
    """
    Given a job id, if no job with such id exist, or if the job exist but has no embedding
    or its embedding is not valid an empty list is returned, otherwise the first 20 most similar jobs to the job
    are returned in a list.
    Similarity is computed using the cosine similarity. Jobs with no embedding are not considered.
    NOTE: this implementation is something that i quickly put together and
    not something that could/should be used in production, it get basically all jobs
    from the db and compares their embedding with the one of the job we are looking similar items for.
    Args:
        job_id:

    Returns:

    """
    input_job = Job.objects(id=job_id)
    if not input_job or "embedding" not in input_job[0] or len(input_job[0]["embedding"]) != 300:
        return []
    input_job = input_job[0]

    other_jobs = Job.objects(Q(id__ne=job_id) & Q(embedding__size=300))
    other_jobs = [job._data for job in other_jobs]
    input_job_embedding = np.array(input_job["embedding"])

    # for each job get the cosine similarity and them sort them
    for job in other_jobs:
        job_embedding = np.array(job["embedding"])
        job["cosine_similarity"] = \
            dot(input_job_embedding, job_embedding) \
            / (norm(input_job_embedding) * norm(job_embedding))
    other_jobs = sorted(other_jobs, key=lambda x: x["cosine_similarity"], reverse=True)
    other_jobs = other_jobs[:20]

    # remove the added key just to be tidy
    for job in other_jobs:
        job.pop("cosine_similarity", None)
    return other_jobs
