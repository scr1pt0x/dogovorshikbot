# handlers.py
from datetime import datetime
import os
import logging

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ConversationHandler, CommandHandler, MessageHandler, ContextTypes, filters
)

from contract_number import generate_contract_number
from docx_generator import generate_contract_and_schedule, generate_istisna_documents
from utils import generate_schedule, round_up_amount
from paths import OUTPUT_DIR

# Conversation states
(
    CHOOSE_CONTRACT,
    DATE_CONTRACT,
    FIO_SELLER,
    FIO_BUYER,
    PHONE_BUYER,
    FIO_GUARANTOR,
    PHONE_GUARANTOR,
    ITEM_DESC,
    ITEM_QTY,
    PRIME_COST,
    MARKUP,
    ADVANCE,
    TERM_MONTHS,
    PAYDAY,
    PLEDGE,
    CONFIRM,
    ISTISNA_FIO_BUYER,
    ISTISNA_ADDRESS_BUYER,
    ISTISNA_PASSPORT_SN_BUYER,
    ISTISNA_PASSPORT_ISSUED_BY,
    ISTISNA_FIO_SUPPLIER,
    ISTISNA_ADDRESS_SUPPLIER,
    ISTISNA_MFG_DAYS,
    ISTISNA_PHONE_SUPPLIER,
    ISTISNA_PHONE_BUYER,
    ISTISNA_ITEM_NAME,
    ISTISNA_ITEM_PRICE,
    ISTISNA_ITEM_QTY,
    ISTISNA_TOTAL_CHOICE,
    ISTISNA_TOTAL_OVERRIDE,
) = range(30)


# /start
def contract_choice_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["Мурабаха", "Истисна"]], resize_keyboard=True, one_time_keyboard=True)


async def start(update: Update, _: ContextTypes.DEFAULT_TYPE):
    logging.info("START -> CHOOSE_CONTRACT")
    kb = contract_choice_keyboard()
    await update.message.reply_text("Выберите договор:", reply_markup=kb)
    return CHOOSE_CONTRACT


async def choose_contract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip().lower()
    logging.info("CHOOSE_CONTRACT received: %r", text)
    if "мурабах" in text:
        context.user_data["contract_type"] = "murabaha"
    elif "истисн" in text:
        context.user_data["contract_type"] = "istisna"
    else:
        await update.message.reply_text("Выберите тип договора кнопкой: «Мурабаха» или «Истисна».")
        return CHOOSE_CONTRACT

    await update.message.reply_text(
        "Введите дату заключения договора (ДД.ММ.ГГГГ):",
        reply_markup=ReplyKeyboardRemove(),
    )
    logging.info("CHOOSE_CONTRACT -> DATE_CONTRACT")
    return DATE_CONTRACT


async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dt = datetime.strptime(update.message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await update.message.reply_text("Неверный формат. Введите дату как ДД.ММ.ГГГГ:")
        return DATE_CONTRACT

    context.user_data["data_dogovora_dt"] = dt
    context.user_data["data_dogovora"] = dt.strftime("%d.%m.%Y")
    context.user_data["contract_number"] = generate_contract_number(dt)  # X-YY_MM_DD

    if context.user_data.get("contract_type") == "istisna":
        await update.message.reply_text("Введите ФИО покупателя:")
        return ISTISNA_FIO_BUYER

    await update.message.reply_text("Введите ФИО продавца:")
    return FIO_SELLER


async def ask_fio_seller(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fio_prodavca"] = update.message.text.strip()
    await update.message.reply_text("Введите ФИО покупателя:")
    return FIO_BUYER


async def ask_fio_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fio_pokupatelya"] = update.message.text.strip()
    await update.message.reply_text("Введите номер телефона покупателя:")
    return PHONE_BUYER


async def ask_phone_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tel_pokupatelya"] = update.message.text.strip()
    await update.message.reply_text("Введите ФИО поручителя:")
    return FIO_GUARANTOR


async def ask_fio_guarantor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fio_poruchitelya1"] = update.message.text.strip()
    await update.message.reply_text("Введите номер телефона поручителя:")
    return PHONE_GUARANTOR


async def ask_phone_guarantor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tel_poruchit1"] = update.message.text.strip()
    await update.message.reply_text("Введите полное описание товара:")
    return ITEM_DESC


async def ask_item_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pokupaemy_tov"] = update.message.text.strip()
    await update.message.reply_text("Введите количество товара (целое число):")
    return ITEM_QTY


async def ask_item_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = update.message.text.strip()
    if not s.isdigit() or int(s) <= 0:
        await update.message.reply_text("Количество должно быть положительным целым. Повторите:")
        return ITEM_QTY
    context.user_data["kolichestvo_tov"] = int(s)
    await update.message.reply_text("Введите себестоимость товара (рубли):")
    return PRIME_COST


async def ask_prime_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число (рубли). Повторите:")
        return PRIME_COST
    context.user_data["sebestoimost_tovara"] = round_up_amount(val)
    await update.message.reply_text("Введите наценку (рубли):")
    return MARKUP


async def ask_markup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число (рубли). Повторите:")
        return MARKUP
    context.user_data["nacenka_tov"] = round_up_amount(val)
    await update.message.reply_text("Введите первоначальный взнос (если нет — 0):")
    return ADVANCE


async def ask_advance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число (рубли). Повторите:")
        return ADVANCE
    context.user_data["pervi_vznos"] = round_up_amount(val)
    await update.message.reply_text("Введите срок договора (в месяцах):")
    return TERM_MONTHS


async def ask_term_months(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = update.message.text.strip()
    if not s.isdigit() or int(s) <= 0:
        await update.message.reply_text("Срок должен быть положительным целым. Повторите:")
        return TERM_MONTHS
    context.user_data["srok_dogov"] = int(s)
    await update.message.reply_text("Введите день месяца для оплаты (1–31):")
    return PAYDAY


async def ask_payday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = update.message.text.strip()
    if not s.isdigit():
        await update.message.reply_text("Введите число 1–31:")
        return PAYDAY
    d = int(s)
    if d < 1 or d > 31:
        await update.message.reply_text("День оплаты должен быть 1–31. Повторите:")
        return PAYDAY
    context.user_data["data_opl"] = d

    kb = ReplyKeyboardMarkup([["Да", "Нет"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text("Залог (Да/Нет)?", reply_markup=kb)
    return PLEDGE


async def ask_pledge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = update.message.text.strip().capitalize()
    if ans not in ("Да", "Нет"):
        await update.message.reply_text("Ответьте: Да или Нет")
        return PLEDGE
    context.user_data["zalog"] = ans

    return await ask_confirm(update, context)


async def istisna_ask_fio_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["buyer_fio"] = update.message.text.strip()
    await update.message.reply_text("Введите адрес покупателя:")
    return ISTISNA_ADDRESS_BUYER


async def istisna_ask_address_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["buyer_address"] = update.message.text.strip()
    await update.message.reply_text("Введите серию и номер паспорта покупателя:")
    return ISTISNA_PASSPORT_SN_BUYER


async def istisna_ask_passport_sn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["buyer_passport_series_number"] = update.message.text.strip()
    await update.message.reply_text("Введите кем выдан паспорт покупателя:")
    return ISTISNA_PASSPORT_ISSUED_BY


async def istisna_ask_passport_issued_by(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["buyer_passport_issued_by"] = update.message.text.strip()
    await update.message.reply_text("Введите ФИО поставщика (SheyKey):")
    return ISTISNA_FIO_SUPPLIER


async def istisna_ask_fio_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["supplier_fio"] = update.message.text.strip()
    await update.message.reply_text("Введите адрес поставщика:")
    return ISTISNA_ADDRESS_SUPPLIER


async def istisna_ask_address_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["supplier_address"] = update.message.text.strip()
    await update.message.reply_text("Введите срок изготовления в рабочих днях (0–360):")
    return ISTISNA_MFG_DAYS


async def istisna_ask_mfg_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = (update.message.text or "").strip()
    if not s.isdigit():
        await update.message.reply_text("Введите целое число 0–360.")
        return ISTISNA_MFG_DAYS
    v = int(s)
    if v < 0 or v > 360:
        await update.message.reply_text("Срок изготовления должен быть в диапазоне 0–360.")
        return ISTISNA_MFG_DAYS
    context.user_data["manufacturing_days"] = v
    await update.message.reply_text("Введите телефон поставщика:")
    return ISTISNA_PHONE_SUPPLIER


async def istisna_ask_phone_supplier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["supplier_phone"] = update.message.text.strip()
    await update.message.reply_text("Введите телефон покупателя:")
    return ISTISNA_PHONE_BUYER


async def istisna_ask_phone_buyer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["buyer_phone"] = update.message.text.strip()
    await update.message.reply_text("Введите наименование товара (цвет/размер):")
    return ISTISNA_ITEM_NAME


async def istisna_ask_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["item_name"] = update.message.text.strip()
    await update.message.reply_text("Введите цену товара (рубли):")
    return ISTISNA_ITEM_PRICE


async def istisna_ask_item_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число (рубли). Повторите:")
        return ISTISNA_ITEM_PRICE
    context.user_data["item_price"] = round_up_amount(val)
    await update.message.reply_text("Введите количество товара (целое число):")
    return ISTISNA_ITEM_QTY


async def istisna_ask_item_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s = (update.message.text or "").strip()
    if not s.isdigit() or int(s) <= 0:
        await update.message.reply_text("Количество должно быть положительным целым числом.")
        return ISTISNA_ITEM_QTY
    qty = int(s)
    context.user_data["item_qty"] = qty
    auto_total = context.user_data["item_price"] * qty
    context.user_data["total_cost_auto"] = auto_total
    context.user_data["total_cost_final"] = auto_total

    kb = ReplyKeyboardMarkup([["Оставить авто", "Ввести вручную"]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        f"Авторасчет общей стоимости: {auto_total} руб.\nОставить эту сумму или ввести вручную?",
        reply_markup=kb,
    )
    return ISTISNA_TOTAL_CHOICE


async def istisna_ask_total_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip().lower()
    if "авто" in txt:
        return await ask_confirm(update, context)
    if "вруч" in txt:
        await update.message.reply_text("Введите общую стоимость (рубли):", reply_markup=ReplyKeyboardRemove())
        return ISTISNA_TOTAL_OVERRIDE
    await update.message.reply_text("Выберите кнопкой: «Оставить авто» или «Ввести вручную».")
    return ISTISNA_TOTAL_CHOICE


async def istisna_ask_total_override(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        val = float(update.message.text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число (рубли).")
        return ISTISNA_TOTAL_OVERRIDE
    context.user_data["total_cost_override"] = round_up_amount(val)
    context.user_data["total_cost_final"] = context.user_data["total_cost_override"]
    return await ask_confirm(update, context)


async def ask_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    if ud.get("contract_type") == "istisna":
        qty = int(ud.get("item_qty", 1))
        text = (
            "Проверьте данные:\n\n"
            "Договор: Истисна\n"
            f"Номер: {ud['contract_number']}\n"
            f"Дата: {ud['data_dogovora']}\n\n"
            f"Покупатель: {ud['buyer_fio']}\n"
            f"Адрес покупателя: {ud['buyer_address']}\n"
            f"Телефон покупателя: {ud['buyer_phone']}\n\n"
            f"Поставщик: {ud['supplier_fio']}\n"
            f"Адрес поставщика: {ud['supplier_address']}\n"
            f"Телефон поставщика: {ud['supplier_phone']}\n\n"
            f"Товар: {ud['item_name']}\n"
            f"Цена за единицу: {ud['item_price']} руб.\n"
            f"Количество: {qty}\n"
            f"Срок изготовления: {ud['manufacturing_days']} рабочих дней\n"
            f"Общая стоимость (авто): {ud['total_cost_auto']} руб.\n"
            f"Общая стоимость (итог): {ud['total_cost_final']} руб.\n"
        )
    else:
        qty = int(ud.get("kolichestvo_tov", 1))
        total_sebestoim = ud["sebestoimost_tovara"] * qty
        total_nacenka = ud["nacenka_tov"] * qty
        polnaya = total_sebestoim + total_nacenka

        text = (
            "Проверьте данные:\n\n"
            f"Договор: Мурабаха\n"
            f"Номер: {ud['contract_number']}\n"
            f"Дата: {ud['data_dogovora']}\n\n"
            f"Покупатель: {ud['fio_pokupatelya']}\n"
            f"Телефон: {ud['tel_pokupatelya']}\n\n"
            f"Товар: {ud['pokupaemy_tov']}\n"
            f"Количество: {qty}\n"
            f"Полная стоимость: {polnaya} руб.\n"
            f"Первый взнос: {ud['pervi_vznos']} руб.\n"
            f"Срок: {ud['srok_dogov']} мес.\n"
            f"День оплаты: {ud['data_opl']}\n"
            f"Залог: {ud['zalog']}\n"
        )

    kb = ReplyKeyboardMarkup(
        [["✅ Сгенерировать", "✏️ Исправить"], ["⛔️ Отмена"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(text, reply_markup=kb)
    return CONFIRM


async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()

    if txt.startswith("✅"):
        await update.message.reply_text("Формирую документы...", reply_markup=ReplyKeyboardRemove())
        return await confirm_and_generate(update, context)

    if txt.startswith("✏️"):
        contract_type = context.user_data.get("contract_type", "murabaha")
        context.user_data.clear()
        context.user_data["contract_type"] = contract_type
        await update.message.reply_text("Начнём заново. Введите дату договора (ДД.ММ.ГГГГ):", reply_markup=ReplyKeyboardRemove())
        return DATE_CONTRACT

    if txt.startswith("⛔"):
        context.user_data.clear()
        kb = contract_choice_keyboard()
        await update.message.reply_text("Отменено. Выберите договор:", reply_markup=kb)
        return CHOOSE_CONTRACT

    await update.message.reply_text("Выберите действие кнопками.")
    return CONFIRM


async def confirm_and_generate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    contract_type = ud.get("contract_type", "murabaha")

    if contract_type == "istisna":
        repl = {
            "{{nomer_dogovora}}": ud["contract_number"],
            "{{data_dogovora}}": ud["data_dogovora"],
            "{{buyer_fio}}": ud["buyer_fio"],
            "{{buyer_address}}": ud["buyer_address"],
            "{{buyer_passport_series_number}}": ud["buyer_passport_series_number"],
            "{{buyer_passport_issued_by}}": ud["buyer_passport_issued_by"],
            "{{supplier_fio}}": ud["supplier_fio"],
            "{{supplier_address}}": ud["supplier_address"],
            "{{manufacturing_days}}": ud["manufacturing_days"],
            "{{supplier_phone}}": ud["supplier_phone"],
            "{{buyer_phone}}": ud["buyer_phone"],
            "{{item_name}}": ud["item_name"],
            "{{item_price}}": ud["item_price"],
            "{{item_qty}}": ud["item_qty"],
            "{{total_cost_final}}": ud["total_cost_final"],
        }
        repl["contract_number"] = ud["contract_number"]

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        generated_docs = generate_istisna_documents(data=repl, out_dir=OUTPUT_DIR)
    else:
        qty = int(ud.get("kolichestvo_tov", 1))
        total_sebestoim = ud["sebestoimost_tovara"] * qty
        total_nacenka = ud["nacenka_tov"] * qty
        polnaya_stoimost = total_sebestoim + total_nacenka
        ostatok_dolga = max(0, polnaya_stoimost - ud["pervi_vznos"])

        schedule = generate_schedule(
            start_date=ud["data_dogovora_dt"],
            term=ud["srok_dogov"],
            payday=ud["data_opl"],
            cost=polnaya_stoimost,
            advance=ud["pervi_vznos"],
        )
        ejemes = schedule[0]["amount"] if schedule else 0

        repl = {
            "{{nomer_dogovora}}": ud["contract_number"],
            "{{data_dogovora}}": ud["data_dogovora"],
            "{{fio_prodavca}}": ud["fio_prodavca"],
            "{{fio_pokupatelya}}": ud["fio_pokupatelya"],
            "{{tel_pokupatelya}}": ud["tel_pokupatelya"],
            "{{fio_poruchitelya1}}": ud["fio_poruchitelya1"],
            "{{tel_poruchit1}}": ud["tel_poruchit1"],
            "{{pokupaemy_tov}}": ud["pokupaemy_tov"],
            "{{kolichestvo_tov}}": ud["kolichestvo_tov"],
            "{{polnaya_stoimost_tov}}": polnaya_stoimost,
            "{{sebestoimost_tovara}}": total_sebestoim,
            "{{nacenka_tov}}": total_nacenka,
            "{{pervi_vznos}}": ud["pervi_vznos"],
            "{{srok_dogov}}": ud["srok_dogov"],
            "{{ejemes_oplata}}": ejemes,
            "{{data_opl}}": ud["data_opl"],
            "{{zalog}}": ud["zalog"],
            "{{ostatok_dolga}}": ostatok_dolga,
        }

        for i in range(1, 13):
            if i <= len(schedule):
                row = schedule[i - 1]
                repl[f"{{{{data_plateja{i}}}}}"] = row["date"]
                repl[f"{{{{summa_plateja{i}}}}}"] = row["amount"]
                repl[f"{{{{ostatok_posle_plateja{i}}}}}"] = row["balance"]
            else:
                repl[f"{{{{data_plateja{i}}}}}"] = ""
                repl[f"{{{{summa_plateja{i}}}}}"] = ""
                repl[f"{{{{ostatok_posle_plateja{i}}}}}"] = ""

        repl["contract_number"] = ud["contract_number"]
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        generated_docs = generate_contract_and_schedule(data=repl, out_dir=OUTPUT_DIR)

    try:
        for path in generated_docs:
            with open(path, "rb") as f:
                await update.message.reply_document(f, filename=path.name)
    finally:
        for p in generated_docs:
            try:
                os.remove(p)
            except Exception:
                pass

    try:
        context.user_data.clear()
    except Exception:
        pass
    kb = contract_choice_keyboard()
    await update.message.reply_text("✅ Готово. Хотите заполнить ещё один договор? Выберите:", reply_markup=kb)
    return CHOOSE_CONTRACT


conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", start)],
    states={
        CHOOSE_CONTRACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_contract)],
        DATE_CONTRACT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_date)],
        FIO_SELLER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fio_seller)],
        FIO_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fio_buyer)],
        PHONE_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone_buyer)],
        FIO_GUARANTOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_fio_guarantor)],
        PHONE_GUARANTOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_phone_guarantor)],
        ITEM_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_item_desc)],
        ITEM_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_item_qty)],
        PRIME_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_prime_cost)],
        MARKUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_markup)],
        ADVANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_advance)],
        TERM_MONTHS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_term_months)],
        PAYDAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_payday)],
        PLEDGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_pledge)],
        CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_confirm)],
        ISTISNA_FIO_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_fio_buyer)],
        ISTISNA_ADDRESS_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_address_buyer)],
        ISTISNA_PASSPORT_SN_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_passport_sn)],
        ISTISNA_PASSPORT_ISSUED_BY: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_passport_issued_by)],
        ISTISNA_FIO_SUPPLIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_fio_supplier)],
        ISTISNA_ADDRESS_SUPPLIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_address_supplier)],
        ISTISNA_MFG_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_mfg_days)],
        ISTISNA_PHONE_SUPPLIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_phone_supplier)],
        ISTISNA_PHONE_BUYER: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_phone_buyer)],
        ISTISNA_ITEM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_item_name)],
        ISTISNA_ITEM_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_item_price)],
        ISTISNA_ITEM_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_item_qty)],
        ISTISNA_TOTAL_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_total_choice)],
        ISTISNA_TOTAL_OVERRIDE: [MessageHandler(filters.TEXT & ~filters.COMMAND, istisna_ask_total_override)],
    },
    fallbacks=[CommandHandler("start", start)],
)