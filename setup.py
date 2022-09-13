#!/usr/bin/env python

from distutils.core import setup

setup(
    name="annotinder",
    version="0.4",
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
        "pydantic",
        'authlib',
        'bcrypt'
    ],
    extras_require={
        'dev': [
            'gunicorn',
            'pytest',
            'codecov',
        ]
    },
)
