#!/usr/bin/env python

from distutils.core import setup

setup(
    name="annotinder",
    version="0.4",
    python_requires = '>= 3.9',
    description="Backend for Annotinder",
    author="Kasper Welbers, Wouter van Atteveldt, Farzam Fanitabasi",
    author_email="kasperwelbers@gmail.com",
    packages=["annotinder", "annotinder.api"],
    include_package_data=True,
    zip_safe=False,
    keywords=["API", "text"],
    classifiers=[
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Topic :: Text Processing",
    ],
    install_requires=[
        'python-dotenv',
        'uvicorn[standard]',
        'python-multipart',
        "fastapi",
        "sqlalchemy",
        "sqlalchemy_utils",
        "psycopg2-binary",
        "pydantic",
        'authlib',
        'bcrypt',
        'email_validator',
    ],
    extras_require={
        'dev': [
            'pytest',
            'requests',
            'gunicorn',
            'pytest',
        ]
    },
)
