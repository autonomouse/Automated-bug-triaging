from setuptools import setup, find_packages

import doberman

setup(
    name="doberman",
    version=oil_ci.__version__,
    description="Statistical Analysis of OIL",
    author="Ryan Harper, Darren Hoyland",
    author_email="<ryan.harper@canonical.com>, <darren.hoyland@canonical.com>",
    url="http://launchpad.net/~oil-ci",
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Programming Language :: Python",
        "Topic :: Internet",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Intended Audience :: Developers"],
    entry_points={
        "console_scripts": [
            'oil-stats = doberman.oil_stats:main',
            'oil-cookie = doberman.oil_cookie:main',
        ]
        },
    )
