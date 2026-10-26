import tkinter as tk
from tkinter import messagebox
import requests
import os
import sys
import threading
import time
import shutil

API_URL = os.getenv("MATE_API_URL", "http://127.0.0.1:8000")

# Model selected by default when installed (best-rated model in the paper's evaluation)
PREFERRED_MODEL = os.getenv("OLLAMA_MODEL", "mistral-nemo")

# Fallback list used only if the backend is unavailable
FALLBACK_MODEL_OPTIONS = [
    "mistral-nemo",
    "llama3.1:8b",
    "qwen2.5:14b",
]
INITIAL_MODEL = PREFERRED_MODEL

def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)

def prepare_icon_to_cwd():
    try:
        bundled_icon = resource_path("assets/mate_icon.ico")
        target = os.path.join(os.getcwd(), "assets", "mate_icon.ico")
        if os.path.exists(bundled_icon) and not os.path.exists(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy(bundled_icon, target)
    except Exception as e:
        print(f"Warning: failed to stage icon: {e}")

def _find_ico_path() -> str | None:
    icon_cwd = os.path.join(os.getcwd(), "assets", "mate_icon.ico")
    icon_bundle = resource_path("assets/mate_icon.ico")
    if os.path.exists(icon_cwd):
        return icon_cwd
    if os.path.exists(icon_bundle):
        return icon_bundle
    return None

def apply_icon(window: tk.Tk | tk.Toplevel):
    # Setting the icon twice on the same window makes Tk on Windows drop it
    if getattr(window, "_mate_icon_applied", False):
        return
    ico = _find_ico_path()
    if not ico:
        return
    window._mate_icon_applied = True
    try:
        window.iconbitmap(default=ico)
    except Exception:
        try:
            window.iconbitmap(ico)
        except Exception:
            pass

prepare_icon_to_cwd()

class MATEApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MATE: Mission Assistant for Training and Evaluation")
        apply_icon(self.root)

        # Streaming control state
        self.stop_event = threading.Event()
        self._current_response = None
        self._current_thread = None
        self._lock = threading.Lock()

        menubar = tk.Menu(self.root)
        helpmenu = tk.Menu(menubar, tearoff=0)
        helpmenu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=helpmenu)
        self.root.config(menu=menubar)

        frame = tk.Frame(self.root)
        frame.pack(padx=20, pady=20)

        model_frame = tk.Frame(frame)
        model_frame.pack(fill="x", pady=(0, 10))

        tk.Label(model_frame, text="Model:").pack(side=tk.LEFT)

        # Start with the first alphabetically from fallback
        self.model_var = tk.StringVar(value=INITIAL_MODEL)
        # Show fallback options (sorted) until backend replaces them
        self.model_menu = tk.OptionMenu(model_frame, self.model_var, *sorted(FALLBACK_MODEL_OPTIONS))
        self.model_menu.pack(side=tk.LEFT, padx=(6, 10))

        tk.Label(frame, text="Enter your tactical question:").pack()
        self.entry = tk.Entry(frame, width=70)
        self.entry.pack(pady=10)
        self.entry.bind("<Return>", self.ask_mate)

        btn_frame = tk.Frame(frame)
        btn_frame.pack(pady=5)
        self.ask_button = tk.Button(btn_frame, text="Ask", command=self.ask_mate)
        self.ask_button.pack(side=tk.LEFT, padx=5)
        self.clear_button = tk.Button(btn_frame, text="Clear", command=self.clear_text)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        # Stop button to cancel ongoing streaming
        self.stop_button = tk.Button(btn_frame, text="Stop", command=self.stop_stream, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.text_output = tk.Text(frame, width=80, height=18, wrap="word")
        self.text_output.pack(pady=10)
        self.text_output.config(state=tk.DISABLED)

        self.status = tk.StringVar(value="Checking backend…")
        self.status_label = tk.Label(self.root, textvariable=self.status, anchor="w")
        self.status_label.pack(fill="x", padx=20, pady=(0, 10))

        self.ask_button.config(state=tk.DISABLED)

        threading.Thread(target=self._wait_backend, daemon=True).start()
        threading.Thread(target=self._load_models_from_backend, daemon=True).start()

    def show_about(self):
        messagebox.showinfo(
            "About MATE",
            "MATE is an offline tactical assistant designed for air combat operations.\n\nVersion 1.0"
        )

    def clear_text(self):
        self.entry.delete(0, tk.END)
        self.text_output.config(state=tk.NORMAL)
        self.text_output.delete(1.0, tk.END)
        self.text_output.config(state=tk.DISABLED)

    def _wait_backend(self):
        url = f"{API_URL}/health"
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                r = requests.get(url, timeout=(2, 2))
                if r.status_code == 200:
                    self.status.set("Backend ready.")
                    self.ask_button.config(state=tk.NORMAL)
                    return
            except requests.RequestException:
                pass
            time.sleep(1.5)
        self.status.set("Backend did not respond. Retry or start the server.")

    def _load_models_from_backend(self):
        url = f"{API_URL}/models"
        try:
            r = requests.get(url, timeout=(3, 5))
            r.raise_for_status()
            data = r.json() or {}
            models = data.get("models", []) or []
            if not models:
                return
            # Update the dropdown with backend models (sorted) and
            # select the first alphabetically.
            self.root.after(0, lambda: self._refresh_model_menu(models))
        except Exception as e:
            print(f"Warning: could not fetch models from backend: {e}")

    def _refresh_model_menu(self, models: list[str]):
        models = sorted(models)  # ensure alphabetical on the GUI too
        menu = self.model_menu["menu"]
        menu.delete(0, "end")
        for m in models:
            menu.add_command(label=m, command=lambda v=m: self.model_var.set(v))
        # Pick the preferred model if installed (with or without a tag),
        # otherwise the first alphabetically
        if models:
            preferred = [m for m in models if m == PREFERRED_MODEL or m.startswith(PREFERRED_MODEL + ":")]
            self.model_var.set(preferred[0] if preferred else models[0])

    def _resolve_model(self) -> str:
        return self.model_var.get().strip()

    def ask_mate(self, event=None):
        q = self.entry.get().strip()
        if not q:
            return

        # Ignore if a streaming thread is already running
        if self._current_thread and self._current_thread.is_alive():
            return

        self.status.set("Asking…")
        self.ask_button.config(state=tk.DISABLED)
        self.clear_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # Clear text area before starting
        self.text_output.config(state=tk.NORMAL)
        self.text_output.delete(1.0, tk.END)
        self.text_output.config(state=tk.DISABLED)

        self.stop_event.clear()
        t = threading.Thread(target=self._do_ask_stream, args=(q,), daemon=True)
        with self._lock:
            self._current_thread = t
        t.start()

    def stop_stream(self):
        # Signal cancellation and close the active connection
        self.stop_event.set()
        with self._lock:
            resp = self._current_response
        try:
            if resp is not None:
                resp.close()
        except Exception:
            pass
        # UI feedback
        self.status.set("Cancelling…")
        self.stop_button.config(state=tk.DISABLED)

    def _do_ask_stream(self, question: str):
        """
        Uses /ask_stream with stream=True.
        'Asking…' -> before first byte
        'Answering…' -> after receiving first byte
        'Done.' or 'Cancelled.' -> when finished
        """
        url_stream = f"{API_URL}/ask_stream"
        payload = {"question": question, "model": self._resolve_model()}
        got_first_byte = False

        try:
            with requests.post(url_stream, json=payload, stream=True, timeout=(5, 300)) as r:
                with self._lock:
                    self._current_response = r

                if r.status_code == 404:
                    # No streaming endpoint; fallback to /ask
                    self._clear_stream_state()
                    self._do_ask_non_stream(question)
                    return
                r.raise_for_status()

                for chunk in r.iter_content(chunk_size=1, decode_unicode=True):
                    if self.stop_event.is_set():
                        break
                    if not chunk:
                        continue
                    if not got_first_byte:
                        got_first_byte = True
                        self.root.after(0, lambda: self.status.set("Answering…"))
                    self._append_text(chunk)

        except requests.RequestException as e:
            if self.stop_event.is_set():
                # Cancelled: do not show an error
                pass
            else:
                if not got_first_byte:
                    self._append_text(f"Could not connect to MATE API (stream).\n\nError: {e}\n")
                else:
                    self._append_text(f"\n\n[stream error] {e}\n")
        finally:
            self._clear_stream_state()
            if self.stop_event.is_set():
                self.root.after(0, lambda: self.status.set("Cancelled."))
            else:
                self.root.after(0, lambda: self.status.set("Done."))
            self.root.after(0, lambda: (self.ask_button.config(state=tk.NORMAL),
                                        self.clear_button.config(state=tk.NORMAL),
                                        self.stop_button.config(state=tk.DISABLED)))

    def _clear_stream_state(self):
        with self._lock:
            self._current_response = None
            self._current_thread = None
        # Keep stop_event set until status update

    def _do_ask_non_stream(self, question: str):
        """
        Fallback to /ask (non-streaming mode).
        """
        try:
            url = f"{API_URL}/ask"
            payload = {"question": question, "model": self._resolve_model()}
            r = requests.post(url, json=payload, timeout=(5, 300))
            r.raise_for_status()
            data = r.json()
            answer = data.get("answer", "No response.")
        except requests.RequestException as e:
            answer = f"Could not connect to MATE API.\n\nError: {e}"
        self._set_answer(answer)

    def _append_text(self, piece: str):
        def _update():
            self.text_output.config(state=tk.NORMAL)
            self.text_output.insert(tk.END, piece)
            self.text_output.see(tk.END)
            self.text_output.config(state=tk.DISABLED)
        self.root.after(0, _update)

    def _set_answer(self, answer: str):
        def _update():
            self.text_output.config(state=tk.NORMAL)
            self.text_output.delete(1.0, tk.END)
            self.text_output.insert(tk.END, answer)
            self.text_output.config(state=tk.DISABLED)
            self.status.set("Done.")
            self.ask_button.config(state=tk.NORMAL)
            self.clear_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
        self.root.after(0, _update)


def launch_main_app():
    splash.destroy()
    root = tk.Tk()
    apply_icon(root)
    MATEApp(root)
    root.mainloop()


# Splash screen
splash = tk.Tk()
apply_icon(splash)
splash.title("Loading MATE…")
splash.geometry("420x220")
splash.eval('tk::PlaceWindow . center')
splash.resizable(False, False)

label_splash = tk.Label(splash, text="MATE", font=("Arial", 24))
label_splash.pack(pady=30)

loading_label = tk.Label(splash, text="Loading, please wait…", font=("Arial", 12))
loading_label.pack()

splash.after(1200, launch_main_app)
splash.mainloop()
