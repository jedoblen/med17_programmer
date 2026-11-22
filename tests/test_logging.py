import logging

from med17.core.logging_setup import attach_callback, setup_logging


def test_arquivo_e_callback(tmp_path):
    setup_logging("INFO", tmp_path)
    recebidos = []
    h = attach_callback(lambda m, l: recebidos.append((m, l)))
    logging.getLogger("med17.teste").info("olá")
    logging.getLogger("med17.teste").debug("oculto")
    logging.getLogger("med17").removeHandler(h)
    for hd in logging.getLogger("med17").handlers:
        hd.flush()
    assert len(recebidos) == 1 and "olá" in recebidos[0][0]
    assert "olá" in (tmp_path / "med17.log").read_text(encoding="utf-8")


def test_setup_idempotente(tmp_path):
    setup_logging("INFO", tmp_path)
    setup_logging("INFO", tmp_path)
    assert len(logging.getLogger("med17").handlers) == 2
