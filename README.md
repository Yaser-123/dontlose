# Don'tLose

You bought the thing. The receipt went into a folder. Three weeks later the return window closed and you found out by trying to return it.

Don'tLose is a deadline safety net for receipts, warranties, subscriptions, renewals, library cards, and the document you swore you would deal with. Drop them in, or type what you already know, and the dates that are actually in there show up on a timeline before they sneak past you.

Nothing is sent to a paid AI API.

## Try it

The demo is live at [dontlose.onrender.com](https://dontlose.onrender.com/).

On that copy you can add items by hand and read a text PDF. Photos and Gemma stay on a computer you run yourself, because that server has no Tesseract and no Ollama. The free instance sleeps when nobody is visiting, so the first open can sit on "Gathering your deadlines" for about a minute. Items there are one shared list, and Render can wipe them when the service restarts. For receipts you care about, run it locally. Your files stay on that machine.

## What you can do

- Upload a pile of photos and PDFs, or add an item by hand.
- Read the text (Tesseract for pictures, the PDF's own text when it has some), then let a local model, Gemma 3 4B through Ollama, pull out the item, the merchant, the price, and the dates.
- See the excerpt each fact came from. Confirm it, fix it, or throw it out.
- Attach another document to the same item when a second file is clearly about the same thing.
- Watch a dashboard, a searchable inventory, and a timeline of what is coming up.
- Leave a note on an item. Rename it. Delete a file without deleting the item.
- Set a reminder. Windows pops it up even if the browser tab is closed, as long as Don'tLose is running.

## The one rule

Deadlines are math, not a vibe.

The model can suggest what it saw. A suggestion only becomes a date on the timeline when the document text actually contains it, or when you confirm it yourself. "30 days" does not get a deadline until there is a start date, and until the text (or you) says whether that start is the purchase or the delivery. A fuzzy date like `03/04/2026` waits for you. A renewal that says "every 12 months" is saved as a fact and does not invent next year's date.

If something looks wrong, correct the fact. The deadline is recalculated from that. The old one does not hang around next to it.

## Run it

You need:

- Windows (the reminder popup and the dev script are written for it)
- Python 3.11
- Node.js 20 or newer
- [Ollama](https://ollama.com/), with the model pulled:

```powershell
ollama pull gemma3:4b
```

Photos and scanned pages also need Tesseract. Text PDFs and typing things in by hand work without it.

```powershell
winget install --id UB-Mannheim.TesseractOCR -e --accept-source-agreements --accept-package-agreements
```

If the installer puts `tesseract.exe` somewhere other than `C:\Program Files\Tesseract-OCR\`, set `TESSERACT_CMD` in `.env`.

First time, install the dependencies:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

cd ..\frontend
npm install
```

Then start both halves. The easy way opens each one in its own window:

```powershell
.\scripts\dev.ps1
```

Or do it yourself. API first:

```powershell
cd backend
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Site second:

```powershell
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). API docs, if you want them, are at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

Receipts, the database, and your notes land in `backend/data/`. That folder is yours. It is not part of the git history.

Copy `.env.example` to `.env` only if you want a different model, a different data folder, or a custom Tesseract path. The defaults already talk to Ollama at `http://127.0.0.1:11434` and use `gemma3:4b`.

### Reminders

A reminder is something you save. A deadline on the timeline does not notify you by itself.

Windows shows it at the time you picked, even with the site closed. Don'tLose has to be running. If Windows has app notifications turned off, the Reminders page says so: **Settings → System → Notifications**. Opening the site later still shows the same reminder as a banner until you dismiss it.

## What it's built with

Next.js, TypeScript, and Tailwind on the site. FastAPI and SQLite on the API. PyMuPDF for PDF text. Tesseract for pictures. Ollama for turning that text into fields. The deadline math is plain Python.

## Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest
```

They check that a missing policy does not become a deadline, that manual items calculate real dates, and that the API stores what you sent.

## When something's off

- **A photo fails and mentions Tesseract.** Install it, or set `TESSERACT_CMD`, then hit Reprocess. The error stays on the file until you do.
- **An upload says Ollama isn't running.** Open the Ollama app and reprocess. Text already read from the file is kept.
- **Gemma is taking a while.** A receipt can sit for a minute or two on `gemma3:4b`. The file shows which stage it's in.
- **A date is wrong.** Open the item and correct the fact. The deadline updates from the new value.
- **No Windows popup.** Don'tLose has to be running, and Windows notifications have to be on.

## Contributing

It's MIT. Use it, change it, ship a fix, tell a friend. The repo is [Yaser-123/dontlose](https://github.com/Yaser-123/dontlose).

Pull requests are welcome. A useful one is a bug with a short note on how you hit it, a clearer empty state, or a deadline rule that still refuses to invent a date. Please keep document text on the machine. Don't add a paid API and call it local.

## License

[MIT](LICENSE). Copyright (c) 2026 Don'tLose contributors.
