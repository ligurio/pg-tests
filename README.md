# Postgres Pro regression tests

Этот репозиторий содержит тесты для Postgres Pro/PostgreSQL и скрипты для их запуска.

## Общее описание и решаемые задачи

Фреймворк выполняет две большие задачи:

    Подготовка окружения для тестирования
    Параметризация и запуск тестов

## Список выполняемых тестов

* clean_install — «чистая» установка
  * установка базового набора пакетов, запуск кластера, остановка, тест pg-setup (инициализация базы в другом месте), запуск, остановка
* dev_usage — пригодность для использования разработчиками расширений
  * в Linux: <<< установка набора пакетов для серверной разработки
  * сборка расширения pg_wait_sampling
  * установка полного набора пакетов
  * подключение pg_wait_sampling в shared_preload_libraries, перезапуск сервера
  * выполнение make installcheck для собранного расширения >>>
  * в Windows: <<< установка postgres и perl, тестирование сборки расширения не производится >>>
* extensions — тестирование расширений
  * установка полного набора пакетов
  * тестирование pgbadger — выполнение нескольких запросов, проверка корректности их анализа pgbadger'ом
  * тестирование pg_stat_statements с sr_plan — проверка записи выполненных запросов в pg_stat_statements
* full_install — полная установка
  * установка всех пакетов
  * в Linux: <<< проверка содержимого пакетов по спискам SERVER_APPLICATIONS, CLIENT_APPLICATIONS, DEV_APPLICATIONS
  * проверка исполняемых файлов — проверка подписей в Astra Smolensk; проверка наличия динамически подключаемых библиотек; проверка наличия отладочных символов >>>
  * проверка вывода pg_controldata и SELECT pgpro_edition(), pgpro_version()
  * проверка наличия службы mamonsu в отключённом состоянии, проверка mamonsu --help
  * проверка всех расширений, присутствующих в share/ (CREATE EXTENSION ...)
  * проверка работоспособности простейших функций на языках plpython (2, 3), pltcl, plperl, plpgsql
  * простейший тест passwordheck — проверка значений по умолчанию для нескольких параметров passwordheck
  * простейший тест cfs для enterprise-версий (создание тейблспейса lz4 для 13+, zstd для всех остальных)  
  * в Linux: проверка отсутствия каких-либо файлов в /usr/src/debug/postgrespro*
  * полное удаление инсталляции; после удаления проверка отсутствия процессов postgres*, проверка сохранения каталога data и удаления каталога инсталляции bin/ или всего каталога инсталляции (если data не внутри); в Linux проверка удаления службы mamonsu
* installcheck — прогон регрессионных тестов в режиме installcheck
  * установка всех пакетов
  * загрузка в shared_preload_libraries всех библиотек, требующихся для прохождения installcheck-world
  * подготовка конфигурации сервера, перезапуск
  * скачивание исходников, соответствующих установленной версии сервера
  * в Linux: <<< установка необходимых пакетов (например, perl IPC-Run, Fuse)
  * получение от pg_config параметров конфигурации установленного экземпляра сервера
  * выполнение ./configure с теми же параметрами
  * make installcheck-world EXTRA_TESTS=numeric_big
  * make installcheck для plv8
  * запуск ещё одного экземпляра сервера с другим каталогом данных и спецконфигурацией
  * прогон дополнительных тестов: src/interfaces/libpq, src/test/modules/commit_ts, src/test/modules/test_pg_dump, src/test/modules/snapshot_too_old, src/test/modules/brin, src/test/modules/unsafe_tests, src/contrib/test_decoding
  * прогон sqlsmith (со сборкой sqlsmith и libpqxx из исходников (в тех ОС, где имеется подходящий C++11)) >>>
  * в Windows: <<< развёртывание msys, сборка необходимых пакетов (например, perl IPC-Run)
  * получение от pg_config параметров конфигурации установленного экземпляра сервера
  * выполнение ./configure с теми же параметрами
  * make installcheck-world EXTRA_TESTS=numeric_big >>>
* multimaster_install — развёртывание мультимастера в конфигурации 2 узла плюс рефери
  * создание раширения, инициализация кластера
  * запуск pgbench на обоих узлах
  * проверка состояния кластера, изолирование узла 2, проверка его недоступности в кластере
  * снятия изоляции узла 2, проверка его успешного восстановления
  * остановка pgbench
  * сравнение дампов БД с узлов 1 и 2
* upgrade — обновление до целевой версии
  * миграция с предшествующих версий Postgres Pro, например с STD 11 на STD 12
  * миграция с более низкого продукта Postgres Pro, например с STD 12 на ENT 12
  * миграция с ванильных PostgreSQL (поставляемых pgdg), меньших либо равных тестируемой версии, например, с PostgreSQL 9.6,10,11,12 на Postgres Pro STD 12/Postgres Pro ENT 12
  *  сверка содержимого базы после обновления с содержимым до (с учётом ожидаемых изменений), проверка всех btree-индексов amcheck'ом
  * (при этом тестируется миграция как с помощью pg_upgrade, так и путём выгрузки/восстановления данных, а в качестве наполнения базы используются дампы, формируемые при регрессионых тестах (с некоторыми модификациями для большей полноты))
* upgrade_minor — обновление в рамках той же мажорной версии
  * проверка штатного обновления с предыдущей минорной версии путём обновления пакетов, в качестве исходных версий берётся самая ранняя из поддерживаемых минорных и самая поздняя, например, обновление до STD 11.8.1 тестируется с STD 11.1.1 и STD 11.7.1
  * сверка содержимого базы после обновления с содержимым до
* hotstandby_compat — проверка совместимости новой версии с предыдущими минорными в плане репликации
  * установка рядом с тестируемой версией по очереди двух предыдущих версий (самой ранней из поддерживаемых минорных и самой поздней, например рядом с STD 11.8.1 устанавливается сначала STD 11.1.1, а затем 11.7.1)
  * настройка репликации с передачей файлов WAL, в которой сначала передатчиком является старая, а приёмников новая, а затем наоборот
  * выполнение теста make standbycheck (по инструкции в regress-run.html)

\* Перед выполнением каждого тестового модуля состояние целевой системы сбрасывается, так что каждый отдельный модуль выполняется в чистой конфигурации.

## Поддерживается запуск тестов через скрипт testrun.py и напрямую с помощью pytest.

Скрипт testrun.py используется для запуска локальных тестов, pytest может использоваться как для запуска локальных тестов, так и для запуска тестов на удаленных физических серверах и виртуальных машинах.

Запуск тестов с помощью testrun.py

Образа виртуалок для тестов лежат на webdav﻿﻿.

На всех виртуалках настроен доступ по ssh для пользователей root:TestRoot1 и test:TestPass1, для пользователя test поддерживается режим sudo.

В Windows создан пользователь test с правами администратора и паролем TestRoot1. Виртуальные машины с Windows могут генерироваться автоматически скриптом: https://github.com/alexanderlaw/packer-qemu-templates.git

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
