# Biotechnology Dashboard

A small Streamlit dashboard with a sidebar menu for the seven color-coded
branches of biotechnology. Each branch lives in its own folder under
`Biotechnology/` and is rendered from a `description.md` file.

## Branches

| Color  | Domain                       | Folder                            |
| ------ | ---------------------------- | --------------------------------- |
| Red    | Medical / Pharmaceutical     | `Biotechnology/Red_Medical_Pharmaceutical/` |
| Green  | Agricultural                 | `Biotechnology/Green_Agricultural/`         |
| White  | Industrial                   | `Biotechnology/White_Industrial/`           |
| Blue   | Marine                       | `Biotechnology/Blue_Marine/`                |
| Grey   | Environmental                | `Biotechnology/Grey_Environmental/`         |
| Yellow | Food / Nutrition             | `Biotechnology/Yellow_Food_Nutrition/`      |
| Gold   | Bioinformatics               | `Biotechnology/Gold_Bioinformatics/`        |

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

App opens at http://localhost:8501.

## Deploy

This app is designed for [Streamlit Community Cloud](https://share.streamlit.io):

1. Push this repo to GitHub.
2. Go to https://share.streamlit.io and click **New app**.
3. Point it at this repo and `app.py` as the entry point.
4. Streamlit installs from `requirements.txt` and gives you a public URL.
