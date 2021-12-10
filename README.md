# amcat4annotator-backend

# API calls specifications
This is a short document describing the various API calls across CCS-Annotator modules

## Between CCS-Annotator Manager and CCS-Annotator backend

### postCodingjob
"""  
endpoint: $host$/codingjob  
method: POST  
Posting codingjobs to annotation backend. Backend creates and stores the codingjob  
POST data should be json:
 {"codebook": {.. blob ..},
  "provenance": {.. blob ..},
  "units": [
    {"unit": {.. blob ..}, "gold": true|false},
    # ...
  ]
 }
"""

(where `..blob..` means that the annotator backend does not inspect these json fields, i.e. they are annotator-implementation specific

### getCodingjob
"""  
endpoint: $host$/codingjob/<id>  
method: GET  
GET a coding job from backend, and sent to annotation manager  
GET data is a json, containing (minimum) title, units, and codebook  
"""

### getCodebook
"""  
endpoint: $host$/codingjob/<id>/codebook  
method: GET  
GET the coding book in the coding job <id> from backend, and sent to annotation manager  
GET data is a json  
"""  

## Between CCS-Annotator backend and CCS-Annotator annoTinder/annoQ&A

### getNextUnit
"""  
endpoint: $host$/codingjob/<id>/unit  
method: GET  
GET the next single unit yet to be coded  
GET data is a json containing the unit id and text  
"""   

### setAnnotation
"""  
endpoint: $host$/codingjob/<job_id>/unit/<unit_id>/annotation  
method: POST  
POST (set) annotation for a specific unit  
POST data should be json, containing job_id, unit_id, and annotations (in form of a nested JSON)  
"""  

