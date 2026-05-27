# tools

## Dataset updates

Steps: 

1. structural sanity
    ```console
    uv run validate.py data/
    ```
1. preview ID assignments, then commit
    ```console
    python assign_ids.py data/
    python assign_ids.py data/ --apply
    ```
1. preview mapping, then commit
    ```console
    python map_data.py data/
    python map_data.py data/ --apply
    ```
1. coverage report
    ```console
    python coverage.py data/
    ```
1. once clean, send data to remote
    ```console
    sudo bash zipsync.sh data
    ```

- validate.py: check file names
- assign_ids.py: Make a patient unique ID mapping
- map_data.py: map all available data to known patients
- coverage.py: show what is missing per patient per day
- zipencrypt.py: make an encrypted zip
- zipsync.sh: sync zips to a wireguard remote