import datetime
from mongoengine import *


class Job(DynamicDocument):
    """
    Data of a job offer, required field are the description_text, description_html
    and employer_name.
    """
    job_title = StringField(required=False, max_length=100)
    employer_name = StringField(required=True, max_length=50)
    description_title = StringField(required=False, max_length=300)
    description_text = StringField(required=True)
    description_html = StringField(required=True)
    description_language = StringField(required=True, max_length=3)
    embedding = ListField(FloatField(), max_length=300)

    city = StringField(required=False, max_length=50)
    state = StringField(required=False, max_length=50)
    country = StringField(required=False, max_length=50)

    job_glassdoor_id = StringField(required=False, unique=True, sparse=True, max_length=50)
    employer_glassdoor_id = StringField(required=False, max_length=50)
    date_of_posting = DateTimeField(default=datetime.datetime.utcnow)
    date_last_modify = DateTimeField(default=datetime.datetime.utcnow)
    meta = {
        "indexes": [
            #  #name stands for an hash index, $name stands for a text index, name stands for a normal btree index
            "date_of_posting"
            "date_last_modify",
            "#description_text",
            "#description_title",

            "#title",
            "#city",
            "#state",
            "#country",
            "#employer_name",
            "#glassdoor_employer_id",

            # every string but description_html form a text index

            # text index on name, hqs, industry
            {'fields': ["$job_title", "$description_title", "$description_text", "$city", "$state",
                        "$country", "$employer_name"],
             'default_language': 'english',
             'weights': {"job_title": 4, "description_title": 2, "description_text": 1,
                         "city": 5, "state": 5, "country": 5, "employer_name": 5
                         }

             }
        ]
    }
