#!/usr/bin/env python

from distutils.core import setup

setup(
    name="amcat4annotator",
    version="0.13",
    description="Annotator Backend API for AmCAT4 Text Analysis",
    author="Wouter van Atteveldt, Farzam Fanitabasi",
    author_email="wouter@vanatteveldt.com",
    packages=["amcat4annotator"],
    include_package_data=True,
    zip_safe=False,
    keywords=["API", "text"],
    classifiers=[
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Topic :: Text Processing",
    ],
    install_requires=[
        "Flask",
        "Flask-HTTPAuth",
        "flask-cors",
        "peewee",
        'authlib',
        'bcrypt'
    ],
    extras_require={
        'dev': [
            'pytest',
            'pytest-flask',
            'codecov',
        ]
    },
)
