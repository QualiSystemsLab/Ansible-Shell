from setuptools import setup, find_packages
import os

with open(os.path.join('version.txt')) as version_file:
    version_from_file = version_file.read().strip()

with open('requirements.txt') as f_required:
    required = f_required.read().splitlines()

with open('test_requirements.txt') as f_tests:
    required_for_tests = f_tests.read().splitlines()

setup(
    name="cs-ansible-second-gen",
    author="Quali",
    author_email="support@qualisystems.com",
    description="A package for sharing command logic between ansible 2G services - admin and regular flavor",
    packages=find_packages(),
    test_suite='nose.collector',
    test_requires=required_for_tests,
    package_data={'': ['*.txt']},
    install_requires=required,
    version=version_from_file,
    include_package_data=True,
    keywords="ansible cloudshell configuration configuration-manager second-gen 2G-Shell",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: Software Development :: Libraries",
        "License :: OSI Approved :: Apache Software License",
    ]
)