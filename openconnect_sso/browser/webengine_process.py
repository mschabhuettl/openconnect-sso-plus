import asyncio
import json
import multiprocessing
import signal
import sys
from urllib.parse import urlparse

import attr

# Prefer importlib.resources, fallback to backport for Python <3.8
try:
    import importlib.resources as importlib_resources
except ModuleNotFoundError:
    import importlib_resources
import structlog
import html as html_utils

from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSlot, QLocale
from PyQt6.QtNetwork import QNetworkCookie, QNetworkProxy
from PyQt6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineScript,
    QWebEngineClientCertificateSelection,
    QWebEngineWebAuthUxRequest,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication, QSizePolicy, QVBoxLayout, QWidget

from openconnect_sso import config
from .webauthdialog import WebAuthUXDialog

app = None
logger = structlog.get_logger("webengine")


@attr.s
class Url:
    url = attr.ib()


@attr.s
class Credentials:
    credentials = attr.ib()


@attr.s
class StartupInfo:
    url = attr.ib()
    credentials = attr.ib()


@attr.s
class SetCookie:
    name = attr.ib()
    value = attr.ib()


class Process(multiprocessing.Process):
    def __init__(self, proxy, display_mode):
        super().__init__()

        self._commands = multiprocessing.Queue()
        self._states = multiprocessing.Queue()
        self.proxy = proxy
        self.display_mode = display_mode

    def authenticate_at(self, url, credentials):
        self._commands.put(StartupInfo(url, credentials))

    async def get_state_async(self):
        while self.is_alive():
            try:
                return self._states.get_nowait()
            except multiprocessing.queues.Empty:
                await asyncio.sleep(0.01)
        if not self.is_alive():
            raise EOFError()

    def run(self):
        # To work around funky GC conflicts with C++ code by ensuring QApplication terminates last
        global app

        signal.signal(signal.SIGTERM, on_sigterm)
        signal.signal(signal.SIGINT, signal.SIG_DFL)

        cfg = config.load()

        argv = sys.argv.copy()
        if self.display_mode == config.DisplayMode.HIDDEN:
            argv += ["-platform", "minimal"]
        app = QApplication(argv)

        language = QLocale.system().name().split("_")[0]
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpAcceptLanguage(language)

        if self.proxy:
            parsed = urlparse(self.proxy)
            if parsed.scheme.startswith("socks5"):
                proxy_type = QNetworkProxy.Socks5Proxy
            elif parsed.scheme.startswith("http"):
                proxy_type = QNetworkProxy.HttpProxy
            else:
                raise ValueError("Unsupported proxy type", parsed.scheme)
            proxy = QNetworkProxy(proxy_type, parsed.hostname, parsed.port)

            QNetworkProxy.setApplicationProxy(proxy)

        # In order to make Python able to handle signals
        force_python_execution = QTimer()
        force_python_execution.start(200)

        def ignore():
            pass

        force_python_execution.timeout.connect(ignore)
        web = WebBrowser(cfg.auto_fill_rules, self._states.put)

        startup_info = self._commands.get()
        logger.info("Browser started", startup_info=startup_info)

        logger.info("Loading page", url=startup_info.url)

        web.authenticate_at(QUrl(startup_info.url), startup_info.credentials)

        web.show()
        rc = app.exec()

        logger.info("Exiting browser")
        return rc

    async def wait(self):
        while self.is_alive():
            await asyncio.sleep(0.01)
        self.join()


def on_sigterm(signum, frame):
    logger.info("Terminate requested.")
    # Force flush cookieStore to disk. Without this hack the cookieStore may
    # not be synced at all if the browser lives only for a short amount of
    # time. Something is off with the call order of destructors as there is no
    # such issue in C++.

    # See: https://github.com/qutebrowser/qutebrowser/commit/8d55d093f29008b268569cdec28b700a8c42d761
    cookie = QNetworkCookie()
    QWebEngineProfile.defaultProfile().cookieStore().deleteCookie(cookie)

    # Give some time to actually save cookies
    exit_timer = QTimer(app)
    exit_timer.timeout.connect(QApplication.quit)
    exit_timer.start(1000)  # ms


class WebBrowser(QWebEngineView):
    def __init__(self, auto_fill_rules, on_update):
        super().__init__()
        self._on_update = on_update
        self._auto_fill_rules = auto_fill_rules
        cookie_store = self.page().profile().cookieStore()
        cookie_store.cookieAdded.connect(self._on_cookie_added)
        self.page().loadFinished.connect(self._on_load_finished)
        self.page().selectClientCertificate.connect(self._on_select_client_certificate)
        self.page().webAuthUxRequested.connect(self._on_webauth_requested)

    def createWindow(self, type):
        if type == QWebEnginePage.WebDialog:
            self._popupWindow = WebPopupWindow(self.page().profile())
            return self._popupWindow.view()

    def authenticate_at(self, url, credentials):
        script_source = (
            importlib_resources.files(".".join(__name__.split(".")[:-1]))
            .joinpath("user.js")
            .read_bytes()
            .decode()
        )
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setSourceCode(script_source)
        self.page().scripts().insert(script)

        if credentials:
            logger.info("Initiating autologin", cred=credentials)
            for url_pattern, rules in self._auto_fill_rules.items():
                script = QWebEngineScript()
                script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
                script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
                script.setSourceCode(
                    f"""
// ==UserScript==
// @include {url_pattern}
// ==/UserScript==

function autoFill() {{
    {get_selectors(rules, credentials)}
    setTimeout(autoFill, 1588);
}}
autoFill();
"""
                )
                self.page().scripts().insert(script)

        self.load(QUrl(url))

    def _on_cookie_added(self, cookie):
        logger.debug("Cookie set", name=to_str(cookie.name()))
        self._on_update(SetCookie(to_str(cookie.name()), to_str(cookie.value())))

    def _on_load_finished(self, success):
        url = self.page().url().toString()
        logger.debug("Page loaded", url=url)

        self._on_update(Url(url))

    def _on_select_client_certificate(self, selection):
        logger.info("Select first client Certificate")
        url = self.page().url().toString()
        certificate = selection.certificates()[0]
        text = (
            "<b>Subject:</b> {subj}<br/>"
            "<b>Issuer:</b> {issuer}<br/>"
            "<b>Serial:</b> {serial}".format(
                subj=html_utils.escape(certificate.subjectDisplayName()),
                issuer=html_utils.escape(certificate.issuerDisplayName()),
                serial=bytes(certificate.serialNumber()).decode("ascii"),
            )
        )
        if len(selection.certificates()) > 1:
            text += (
                "<br/><br/><b>Note:</b> Multiple matching certificates "
                "were found, but certificate selection is not "
                "implemented yet!"
            )
        logger.info(text)
        selection.select(certificate)
        self.load(QUrl(url))

    def _on_webauth_requested(self, request):
        logger.debug("WebAuth UX requested")
        self.webAuth = WebAuthUXDialog(self, request)
        self.webAuth.setModal(False)
        self.webAuth.setWindowFlags(
            self.webAuth.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        request.stateChanged.connect(self._on_webauth_statechanged)
        self.webAuth.show()

    @pyqtSlot("QWebEngineWebAuthUxRequest::WebAuthUxState")
    def _on_webauth_statechanged(self, state):
        if (
            state == QWebEngineWebAuthUxRequest.WebAuthUxState.Completed
            or state == QWebEngineWebAuthUxRequest.WebAuthUxState.Cancelled
        ):
            if self.webAuth is not None:
                self.webAuth.close()
                self.webAuth = None
        else:
            self.webAuth.updateDisplay()


class WebPopupWindow(QWidget):
    def __init__(self, profile):
        super().__init__()
        self._view = QWebEngineView(self)

        super().setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        super().setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        layout = QVBoxLayout()
        super().setLayout(layout)
        layout.addWidget(self._view)

        self._view.setPage(QWebEnginePage(profile, self._view))

        self._view.titleChanged.connect(super().setWindowTitle)
        self._view.page().geometryChangeRequested.connect(
            self.handleGeometryChangeRequested
        )
        self._view.page().windowCloseRequested.connect(super().close)

    def view(self):
        return self._view

    @pyqtSlot("const QRect")
    def handleGeometryChangeRequested(self, newGeometry):
        self._view.setMinimumSize(newGeometry.width(), newGeometry.height())
        super().move(newGeometry.topLeft() - self._view.pos())
        super().resize(0, 0)
        super().show()


def to_str(qval):
    return bytes(qval).decode()


def get_selectors(rules, credentials):
    statements = []
    for rule in rules:
        selector = json.dumps(rule.selector)
        if rule.action == "stop":
            statements.append(
                f"""var elem = document.querySelector({selector}); if (elem) {{ return; }}"""
            )
        elif rule.fill:
            value = json.dumps(getattr(credentials, rule.fill, None))
            if value:
                statements.append(
                    # f"""var elem = document.querySelector({selector}); if (elem) {{ elem.dispatchEvent(new Event("focus")); elem.value = {value}; elem.dispatchEvent(new Event("blur")); }}"""
                    f"""var elem = document.querySelector({selector}); if (elem) {{ elem.dispatchEvent(new Event("focus")); elem.value = {value}; elem.dispatchEvent(new Event('input', {{bubbles: true}})); /*elem.dispatchEvent(new Event("blur"));*/ }}"""
                )
            else:
                logger.warning(
                    "Credential info not available",
                    type=rule.fill,
                    possibilities=dir(credentials),
                )

        elif rule.action == "click":
            statements.append(
                # f"""var elem = document.querySelector({selector}); if (elem) {{ elem.dispatchEvent(new Event("focus")); elem.click(); }}"""
                f"""var elem = document.querySelector({selector}); if (elem) {{ var click_delay=728; elem.dispatchEvent(new Event("focus")); setTimeout(function() {{ document.querySelector({selector}).click(); }}, click_delay); }}"""
            )
    return "\n".join(statements)
