A custom client made in django, you can try it out
at localhost:8000 after doing

```
python manage.py runserver
```



The directory (and files) follows the structure
of django projects. 
The code for the client can be found in the "custom_client/" 
directory.

There are three views:

 - job_details: given a job id, display information about that job offer
 - company_details: given a company id, display information about that company
 - search: essentially the index, given a search form it will return/contain search
    results either for jobs or companies