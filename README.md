# PostgreSQL regression tests

Этот репозиторий содержит тесты для PostgreSQL и скрипты для их запуска.

## Рекомендации для тестов:

- http://www.sqlstyle.guide/

## Настройка сервера для запуска тестов:

- пакеты для RPM-based дистрибутивов:
```
yum install -y git libvirt libvirt-python qemu-kvm gcc openssl-devel python-devel python-cffi vim
```
- установить PyPA:
```
curl -O https://bootstrap.pypa.io/get-pip.py
python get-pip.py
```
- установить зависимости для [Ansible](https://www.ansible.com/) (см. также
[инструкцию](http://docs.ansible.com/ansible/intro_installation.html)):
```
	Debian-based: apt install -y libssl-dev gcc
	RPM-based: yum install -y openssl-devel gcc
```
- установить Ansible и модули для него: ```pip install ansible pywinrm paramiko```
- если для запуска ВМ скрипт не найдет шаблон ВМ, то он его загрузит, но можно
заранее загрузить все шаблоны виртуальных машин. Например так: ```wget -np -nd
-A qcow2 -r -l 1 http://webdav.l.postgrespro.ru/DIST/vm-images/test/```
- для доступа по SSH ключам в гостевые ОС нужно скопировать ключи из репозитория:
```
	cp static/id_rsa ~/.ssh/id_rsa.pg
	cat static/authorized_keys >> ~/.ssh/authorized_keys
	chmod 700 ~/.ssh/id_rsa
```
и добавить их вместе с полезными опциями в конфиг ~/.ssh/config:
```
	Compression yes
	CompressionLevel 9
	HashKnownHosts yes
	ServerAliveInterval 120
	TCPKeepAlive no

	Host *
        User							test
        UseRoaming=no
        IdentityFile                    ~/.ssh/id_rsa.pg
```

### Настройки ОС для тестирования

Все необходимые настройки выполняются сценарием для Ansible в static/playbooks_prep_env.yml,
который запускается скриптом testrun.py перед запуском теста. Но можно запустить и вручную:
```
$ cat static/inventory
ubuntu1604 ansible_host=127.0.0.1 ansible_become_pass=TestRoot1 ansible_ssh_pass=TestPass1 ansible_user=test ansible_become_user=root
$ ansible-playbook static/playbook-prepare-env.yml -i static/inventory -c paramiko --limit ubuntu1604
$ ansible ubuntu1604 -m setup -i static/inventory -c paramiko
```
