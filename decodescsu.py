LONG_COMBINATIONS_ADDITIONAL_SIZE = 2
MOST_SIGNIFICANT_BYTE_MULT = 0x100
REPLACEMENT_CHAR = "\ufffd"
FIRST_HIGH_SURROGATE_CODE = 0xD800
FIRST_LOW_SURROGATE_CODE = 0xDC00
FIRST_PRIV_CHAR_CODE = 0xE000
# Single byte mode
QUOTE_WIN_0_1BYTE = 0x01
TAB_CODE = 0x09
DEFINE_EXTENDED_1BYTE = 0x0B
RESERVED_1BYTE = 0x0C
QUOTE_UNICODE_1BYTE = 0x0E
BYTE_CHOOSE_UNICODE_MODE = 0x0F
CHOOSE_DYN_WIN_0_1BYTE = 0x10
DEFINE_DYN_WIN_0_1BYTE = 0x18
SPACE_CODE = 0x20
WIN_SIZE = 0x80
STATIC_WINS = (
    0x0000,
    0x0080,
    0x0100,
    0x0300,
    0x2000,
    0x2080,
    0x2100,
    0x3000
)
DYN_WINS_INIT = (
    0x0080,
    0x00C0,
    0x0400,
    0x0600,
    0x0900,
    0x3040,
    0x30A0,
    0xFF00
)
DEF_DYN_WIN_1ST_PRIV_CODE = 0x68
DEF_DYN_WIN_LAST_BMP_CODE = 0xA7
DEF_DYN_WIN_1ST_PRIV_ADD_OFFSET = 0xAC00
DEF_DYN_WIN_1ST_CROSS_BORDER_CODE = 0xF9
DEF_DYN_WIN_CROSS_BORDER_OFFSETS = (
    0x00C0,
    0x0250,
    0x0370,
    0x0530,
    0x3040,
    0x30A0,
    0xFF60,
)
DEF_EXT_WIN_PARAMS_SPLIT = 0x2000
FIRST_NON_BMP_CHAR_CODE = 0x10000
# Unicode mode
CHOOSE_DYN_WIN_0_UNI = 0xE0
DEFINE_DYN_WIN_0_UNI = 0xE8
QUOTE_UNICODE_UNI = 0xF0
DEFINE_EXTENDED_UNI = 0xF1
RESERVED_UNI = 0xF2


def is_high_surrogate_code(char_code):
    return FIRST_HIGH_SURROGATE_CODE <= char_code < FIRST_LOW_SURROGATE_CODE


def is_low_surrogate_code(char_code):
    return FIRST_LOW_SURROGATE_CODE <= char_code < FIRST_PRIV_CHAR_CODE


class SCSUDecoder:
    def __init__(self):
        self.wins = [STATIC_WINS, list(DYN_WINS_INIT)]
        self.decoded_text = ""
        self.current_win = 0
        self.unicode_mode = False
        self.wait_low_surrogate = False
        self.saved_high_surrogate_code = None

    def choose_win(self, chosen_win_index):
        self.current_win = self.wins[1][chosen_win_index]

    def decode_byte(self, byte_to_decode, quote_win_index=-1):
        is_from_dynamic_win = byte_to_decode >= WIN_SIZE
        if quote_win_index == -1:
            win_offs = self.current_win if is_from_dynamic_win else 0
        else:
            win_offs = self.wins[is_from_dynamic_win][quote_win_index]
        char_code = win_offs + byte_to_decode % WIN_SIZE
        self.decoded_text += chr(char_code)

    def catch_not_valid_byte_combination(self):
        self.decoded_text += REPLACEMENT_CHAR

    def decode_uni_mode_code(self, char_code):
        if self.wait_low_surrogate:
            self.wait_low_surrogate = False
            if is_low_surrogate_code(char_code):
                surrogate_pair = chr(self.saved_high_surrogate_code) + chr(char_code)
                self.decoded_text += surrogate_pair
                return
            self.catch_not_valid_byte_combination()
        if is_high_surrogate_code(char_code):
            self.wait_low_surrogate = True
            self.saved_high_surrogate_code = char_code
            return
        if is_low_surrogate_code(char_code):
            self.catch_not_valid_byte_combination()
            return
        self.decoded_text += chr(char_code)

    def def_dynamic_win(self, offset, index):
        if offset:
            self.wins[1][index] = offset
            self.current_win = offset
        else:
            self.catch_not_valid_byte_combination()


def convert_code_to_offset(win_code):
    if win_code < DEF_DYN_WIN_1ST_PRIV_CODE:
        return win_code * WIN_SIZE
    if win_code <= DEF_DYN_WIN_LAST_BMP_CODE:
        return win_code * WIN_SIZE + DEF_DYN_WIN_1ST_PRIV_ADD_OFFSET
    if win_code >= DEF_DYN_WIN_1ST_CROSS_BORDER_CODE:
        cross_border_offs_index = win_code - DEF_DYN_WIN_1ST_CROSS_BORDER_CODE
        return DEF_DYN_WIN_CROSS_BORDER_OFFSETS[cross_border_offs_index]
    return


def define_dynamic_win(byte_code, win_index, decoder):
    offs = convert_code_to_offset(byte_code)
    decoder.def_dynamic_win(offs, win_index)


def define_dynamic_win_ext(combined_bytes, decoder):
    win_index = combined_bytes // DEF_EXT_WIN_PARAMS_SPLIT
    win_offs_id = combined_bytes % DEF_EXT_WIN_PARAMS_SPLIT
    win_offset = FIRST_NON_BMP_CHAR_CODE + win_offs_id * WIN_SIZE
    decoder.def_dynamic_win(win_offset, win_index)


def check_size_of_byte_combination(lead_byte):
    is_define_extended = lead_byte == DEFINE_EXTENDED_1BYTE
    is_quote_unicode = lead_byte == QUOTE_UNICODE_1BYTE
    if is_define_extended or is_quote_unicode:
        return LONG_COMBINATIONS_ADDITIONAL_SIZE
    is_quote_single_byte = QUOTE_WIN_0_1BYTE <= lead_byte < TAB_CODE
    is_define_win = DEFINE_DYN_WIN_0_1BYTE <= lead_byte < SPACE_CODE
    if is_quote_single_byte or is_define_win:
        return 1
    return 0


def check_size_of_byte_combination_uni(lead_byte):
    is_define_extended = lead_byte == DEFINE_EXTENDED_UNI
    is_quote_unicode = lead_byte == QUOTE_UNICODE_UNI
    if is_define_extended or is_quote_unicode:
        return LONG_COMBINATIONS_ADDITIONAL_SIZE
    is_choose_win = CHOOSE_DYN_WIN_0_UNI <= lead_byte < DEFINE_DYN_WIN_0_UNI
    if is_choose_win or lead_byte == RESERVED_UNI:
        return 0
    return 1


def decode_long_byte_combination(tag_byte, args_bytes, decoder):
    combined_args = int.from_bytes(args_bytes)
    if tag_byte == DEFINE_EXTENDED_1BYTE:
        define_dynamic_win_ext(combined_args, decoder)
    else:
        decoder.decode_uni_mode_code(combined_args)


def decode_long_byte_combination_uni(tag_byte, args_bytes, decoder):
    combined_args = int.from_bytes(args_bytes)
    if tag_byte == DEFINE_EXTENDED_UNI:
        define_dynamic_win_ext(combined_args, decoder)
        decoder.unicode_mode = False
    else:
        decoder.decode_uni_mode_code(combined_args)


def decode_short_byte_combination(tag_byte, arg_byte, decoder):
    arg = int.from_bytes(arg_byte)
    if tag_byte < TAB_CODE:
        win_index = tag_byte - QUOTE_WIN_0_1BYTE
        decoder.decode_byte(arg, win_index)
    else:
        win_index = tag_byte - DEFINE_DYN_WIN_0_1BYTE
        define_dynamic_win(arg, win_index, decoder)


def decode_short_byte_combination_uni(tag_byte, arg_byte, decoder):
    arg = int.from_bytes(arg_byte)
    if DEFINE_DYN_WIN_0_UNI <= tag_byte < QUOTE_UNICODE_UNI:
        win_index = tag_byte - DEFINE_DYN_WIN_0_UNI
        define_dynamic_win(arg, win_index, decoder)
        decoder.unicode_mode = False
    else:
        char_code = MOST_SIGNIFICANT_BYTE_MULT * tag_byte + arg
        decoder.decode_uni_mode_code(char_code)


def decode_single_byte(byte_to_decode, decoder):
    if byte_to_decode == BYTE_CHOOSE_UNICODE_MODE:
        decoder.unicode_mode = True
    elif CHOOSE_DYN_WIN_0_1BYTE <= byte_to_decode < DEFINE_DYN_WIN_0_1BYTE:
        win_index = byte_to_decode - CHOOSE_DYN_WIN_0_1BYTE
        decoder.choose_win(win_index)
    elif byte_to_decode == RESERVED_1BYTE:
        decoder.catch_not_valid_byte_combination()
    else:
        decoder.decode_byte(byte_to_decode)

def check_lead_byte_in_waiting_low_surrogate(lead_byte, add_bytes_amount, decoder):
    if add_bytes_amount:
        if lead_byte >= DEFINE_EXTENDED_1BYTE:
            return
    else:
        is_choose_win = CHOOSE_DYN_WIN_0_1BYTE <= lead_byte < DEFINE_DYN_WIN_0_1BYTE
        if lead_byte == BYTE_CHOOSE_UNICODE_MODE or is_choose_win:
            return
    decoder.catch_not_valid_byte_combination()
    decoder.wait_low_surrogate = False


def decode_in_unicode_mode(bytes_to_decode, decoder):
    bytes_left = bytes_to_decode
    while len(bytes_left) and decoder.unicode_mode:
        most_signif_byte = bytes_left[0]
        additional_bytes_amount = check_size_of_byte_combination_uni(most_signif_byte)
        additional_bytes = bytes_left[1 : additional_bytes_amount + 1]
        bytes_left = bytes_left[additional_bytes_amount + 1 :]
        if len(additional_bytes) == additional_bytes_amount:
            if additional_bytes_amount > 1:
                decode_long_byte_combination_uni(most_signif_byte, additional_bytes, decoder)
            elif additional_bytes_amount:
                decode_short_byte_combination_uni(most_signif_byte, additional_bytes, decoder)
            else:
                if most_signif_byte == RESERVED_UNI:
                    decoder.catch_not_valid_byte_combination()
                    break
                win_index = most_signif_byte - CHOOSE_DYN_WIN_0_UNI
                decoder.choose_win(win_index)
                decoder.unicode_mode = False
        else:
            decoder.catch_not_valid_byte_combination()
    return bytes_left


def decode_scsu(bytes_to_decode):
    scsu_decoder = SCSUDecoder()
    bytes_left = bytes_to_decode
    while len(bytes_left):
        current_byte = bytes_left[0]
        additional_bytes_amount = check_size_of_byte_combination(current_byte)
        if scsu_decoder.wait_low_surrogate:
            check_lead_byte_in_waiting_low_surrogate(
                current_byte, additional_bytes_amount, scsu_decoder
            )
        additional_bytes = bytes_left[1 : additional_bytes_amount + 1]
        bytes_left = bytes_left[additional_bytes_amount + 1 :]
        if len(additional_bytes) == additional_bytes_amount:
            if additional_bytes_amount > 1:
                decode_long_byte_combination(current_byte, additional_bytes, scsu_decoder)
            elif additional_bytes_amount:
                decode_short_byte_combination(current_byte, additional_bytes, scsu_decoder)
            else:
                decode_single_byte(current_byte, scsu_decoder)
        else:
            scsu_decoder.catch_not_valid_byte_combination()
        if scsu_decoder.unicode_mode:
            bytes_left = decode_in_unicode_mode(bytes_left, scsu_decoder)
    return scsu_decoder.decoded_text
