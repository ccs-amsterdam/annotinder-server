#!/usr/bin/env python

from distutils.core import setup

setup(
    name="amcat4annotator",
    version="0.22",
    description="Annotator Backend API for AmCAT4 Text Analysis",
    author="Wouter van Atteveldt, Farzam Fanitabasi, Kasper Welbers",
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
        "fastapi",
        "peewee",
        'authlib',
        'bcrypt'
    ],
    extras_require={
        'dev': [
            'pytest',
            'codecov',
        ]
    },
)
