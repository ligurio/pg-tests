# PostgreSQL regression tests

Этот репозиторий содержит тесты для PostgreSQL и скрипты для их запуска.

## Общее описание и решаемые задачи

Фреймворк выполняется две большие задачи:

    Подготовка окружения для тестирования
    Параметризация и запуск тестов

## Поддерживается запуск тестов через скрипт testrun.py и напрямую с помощью pytest.

Скрипт testrun.py используется для запуска локальных тестов, pytest может использоваться как для запуска локальных тестов, так и для запуска тестов на удаленных физических серверах и виртуальных машинах.

Запуск тестов с помощью testrun.py

Образа виртуалок для тестов лежат на webdav﻿﻿.

На всех виртуалках настроен доступ по ssh для пользователей root:TestRoot1 и test:TestPass1, для пользователя test поддерживается режим sudo.

В Windows создан пользователь test с правами Admin и паролем TestRoot1. Виртуальные машины с Windows могут генерироваться автоматически  скриптом: https://github.com/alexanderlaw/packer-qemu-templates.git

Запуск локальных тестов с использованием скрипта testrun.py:

-h – помощь

Опции, которые относятся к продукту

--product_name – имя продукта, доступные значения: postgresql, postgrespro

--product_edition – тип продукта, доступные значения: std, ent, std-cert, ent-cert

--product_version – версия продукта

--product_milestone – статус продукта, доступные значения: beta, либо не задается, если нужна установка из основного репозитория

--target – операционная система, на которой будет проводится тестирование

--keep – удалить или сохранить виртуальную машину после выполнения тестов

--export – сохранять ли результаты тестирования в виде отчета

--test – имена тестов, которые будут выполнены (опциональный параметр, если не задан, будут выполнены все тесты из каталога tests/, может принимать имя каталога, из которого будут запущены все тесты, например: --test tests_install/)

## Функции скрипта testrun.py

    Скрипт командной строки
    Развертывание виртуалок
    Запуск ansible playbook для установки пакетов на тестируемой виртуалке
    Заливка фреймворка тестирования на виртуалку
    Запуск тестов на виртуалке
    Получение отчетности


## Системные требования к окружению

Необходимо создать каталог /pgpro на диске. В данном каталоге будут хранится виртуальные машины, используемые для запуска тестов.
- пакеты для RPM-based дистрибутивов:
```
yum install -y git libvirt libvirt-python qemu-kvm gcc openssl-devel python-devel python-cffi vim samba
```
Версия пакета libvirt должна быть не ниже 2.0.

## Рекомендации для тестов:

- http://www.sqlstyle.guide/

## Настройка сервера для запуска тестов:

- пакеты для RPM-based дистрибутивов:
```
yum install -y git libvirt libvirt-python qemu-kvm gcc openssl-devel python-devel python-cffi vim samba
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
- установить Ansible и модули для него: ```sudo pip install ansible pywinrm paramiko```
- если для запуска ВМ скрипт не найдет шаблон ВМ, то он его загрузит, но можно
заранее загрузить все шаблоны виртуальных машин. Например так: ```wget -np -nd
-A qcow2 -r -l 1 http://dist.l.postgrespro.ru/vm-images/test/```
- для доступа по SSH ключам в гостевые ОС нужно скопировать ключи из репозитория:
```
	cp static/id_rsa ~/.ssh/id_rsa.pg-tests
	cat static/authorized_keys >> ~/.ssh/authorized_keys
	chmod 700 ~/.ssh/id_rsa.pg-tests
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
        IdentityFile                    ~/.ssh/id_rsa.pg-tests
```

### Настройки тестируемой ОС

Все необходимые настройки выполняются сценарием Ansible tests/playbook-prepare-env.yml (tests_intall/playbook-prepare-env.yml),
который запускается скриптом testrun.py перед собственно запусками тестов в целевой ОС.
