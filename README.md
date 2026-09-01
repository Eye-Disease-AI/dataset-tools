# tools

## Dataset updates

Steps: 

1. structural sanity
    ```console
    uv run validate.py data/
    ```
1. preview ID assignments, then commit
    ```console
    uv run  assign_ids.py data/
    uv run  assign_ids.py data/ --apply
    ```
1. preview mapping, then commit
    ```console
    uv run  map_data.py data/
    uv run  map_data.py data/ --apply
    ```
1. coverage report
    ```console
    uv run  coverage.py data/
    ```
1. dataset statistics
    ```console
    uv run  stats.py data/
    ```
1. preview Label Studio tasks, then write them
    ```console
    uv run  make_labelstudio_jsons.py data/
    uv run  make_labelstudio_jsons.py data/ --apply
    ```
1. once clean, zip data
    ```console
    uv run zipencrypt.py data/
    ```
1. send data to remote
    ```console
    bash zipsync.sh <wg_interface_name> <path_to_send> <username>@<host>:<path>
    ```

- validate.py: check file names
- assign_ids.py: Make a patient unique ID mapping
- map_data.py: map all available data to known patients
- coverage.py: show what is missing per patient per day
- stats.py: dataset size, per-type coverage, questionnaire answer distributions
- make_labelstudio_jsons.py: build Label Studio import tasks (one per visit) from mapping.json
- zipencrypt.py: make an encrypted zip
- zipsync.sh: sync zips to a wireguard remote