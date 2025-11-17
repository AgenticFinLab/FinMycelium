"""
This is a test to check if the setup.py file is correctly configured
"""

from projinit import config

import cdemo


if __name__ == "__main__":

    # Initialize the project
    test_config = config.Config()
    # Get the details of the configuration
    data_info = test_config.data
    model_info = test_config.model
    train_info = test_config.train
    log_info = test_config.logging
    eval_info = test_config.eval
    # Convert to dict format, with data_info as an example
    data_info_dict = data_info._asdict()
    print(data_info)
    print(data_info_dict)

    print("Setup script executed successfully.")
