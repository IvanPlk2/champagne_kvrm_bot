

def get_when_text(date_start, date_end, is_festival):

    if is_festival:
        pass

    if is_festival:
        if date_start == date_end:
            return date_start.strftime("%d.%m.%y")
        else:
            start_txt = date_start.strftime("%d.%m.%y")
            end_txt = date_end.strftime("%d.%m.%y")
            return '-'.join([start_txt, end_txt])

    return date_start.strftime("%d.%m.%y %H:%M")