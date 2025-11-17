### Mandatory Reading -- Must read


This repo provides a template for Python projects, including a setup script, configuration files, and a basic directory structure. It is designed to help developers quickly set up a new Python project with best practices in mind. With this template, your project named `cdemo` will be used as an internal package in python coding. By doing so, any module you created under the `cdemo/` can be imported directly after a `pip install -e .` command.

After creating a new Python project using this template, you still need to make the following changes:

1. To ensure clarity and proper identification, please rename the `cdemo` directory to reflect the designated name of your project.
2. Proceed to the `description.txt` file and update its contents to provide a concise and accurate summary of the project. This description serves as a formal overview, and precision is paramount.
3. Change the `setup.py` file by updating the version in `get_version` function and `name`, `description`, `url`, `keywords` fields of the `setuptools.setup`, where the `url` is the link address of the current repo.<img width="769" height="822" alt="c9134dd2ee5bb07ce9c146214ff9a477" src="https://github.com/user-attachments/assets/187bbd46-52e0-40d4-81bb-5569fd9bcbf7" />

4. Update the `README.md` file to provide a description of your project.   
5. Remove the `examples/Test/test.py` file if you don't need it. Then, create your own method based on your code under `cdemo/` directory.

Note that the `examples/` is a folder to allow you to place any method implemented based on the `cdemo`.


**Potential bugs**

If the program encounters bugs during installing site-packages, please try updating the setuptools first:
```python
 pip install -- upgrade setuptools
```


### Structure

```text
.
├── README.md               # Overview and structure of the project.
├── docs/
│   ├── files               # Various documentations related to the research.
│   ├── Progress-record.md  # Record of progress and findings.
│   ├── reference.md        # Record of all papers used in the project.
├── configs/                # Configuration files for the project.
├── examples/               # Exact demos and methods implemented based on the code from `cdemo/`.
├── cdemo/
│   ├── ???
└── requirements.txt        # List of dependencies required to run the project.
```

Please note that the `cdemo/` directory serves as an internal Python package. Once you run `pip install -e .`, any module within `cdemo/` can be imported directly in your code. As such, ensure that the code placed in `cdemo/` is well-structured and functions as the foundational codebase for all method implementations located in the `examples/` directory.


### Coding Format Template

Strictly follow the [Google's Python Coding Style](https://google.github.io/styleguide/pyguide.html) to organize the coding. If you do not read such a detailed guidance, please directly follow the [coding template](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html).


### Additional Packages

One may need to use additional packages to control the configuration and logging of the project. Please refer to the [project-init](https://github.com/AgenticFinLab/project-init) for details.


After installing this package, please run the following command to test.

```console

python examples/Test/test.py -c configs/Test/test.yml -b FirstTest -p MyTest
```


### Github desktop
For effective team collaboration and the maintenance of a clear commit history, the use of GitHub Desktop is mandated for project management. Adherence to the standardized commit practices outlined in the following guide is required: [Research Preparation](https://github.com/AgenticFinLab/group-resource/blob/main/materials/research-preparation.md).

Core Requirements:

Standardized Commit Messages: Each commit must be accompanied by a clear and descriptive message that succinctly explains the purpose and scope of the changes.

Atomic Commits: It is imperative that each commit encapsulates a single, logical, and complete unit of work, such as a feature implementation or a bug fix.

Regular Synchronization: Regularly pull updates from the remote repository to stay current. Prior to pushing local changes, ensure all merge conflicts are resolved.

Compliance with this protocol is essential for facilitating seamless team collaboration and streamlining the code review process.
