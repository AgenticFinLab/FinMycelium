## Mandatory Reading -- Must read


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
