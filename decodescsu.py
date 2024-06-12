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
STATIC_WINS = (0x0000, 0x0080, 0x0100, 0x0300, 0x2000, 0x2080, 0x2100, 0x3000)
DYN_WINS_INIT = (0x0080, 0x00C0, 0x0400, 0x0600, 0x0900, 0x3040, 0x30A0, 0xFF00)
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


def isHighSurrogateCode(charCode):
    return charCode >= FIRST_HIGH_SURROGATE_CODE and charCode < FIRST_LOW_SURROGATE_CODE


def isLowSurrogateCode(charCode):
    return charCode >= FIRST_LOW_SURROGATE_CODE and charCode < FIRST_PRIV_CHAR_CODE


class scsuDecoderClass:
    def __init__(self):
        self.wins = [STATIC_WINS, list(DYN_WINS_INIT)]
        self.quoteWinIndex = None
        self.decodedBytesAmount = 0
        self.decodedText = ""
        self.currentWin = 0
        self.unicodeMode = False
        self.waitLowSurrogate = False
        self.savedHighSurrogateCode = None

    def chooseWin(self, chosenWinIndex):
        self.currentWin = self.wins[1][chosenWinIndex]

    def decodeByte(self, byteToDecode, quoteWinIndex=-1):
        isFromDynamicWin = byteToDecode >= WIN_SIZE
        if quoteWinIndex == -1:
            winOffs = self.currentWin if isFromDynamicWin else 0
        else:
            isFromDynamicWin = byteToDecode >= WIN_SIZE
            winOffs = self.wins[isFromDynamicWin][quoteWinIndex]
        charCode = winOffs + byteToDecode % WIN_SIZE
        self.decodedText += chr(charCode)

    def catchNotValidByteCombination(self):
        self.decodedText += REPLACEMENT_CHAR

    def decodeUniModeCode(self, charCode):
        if self.waitLowSurrogate:
            if isLowSurrogateCode(charCode):
                surrogatePair = chr(self.savedHighSurrogateCode) + chr(charCode)
                self.decodedText += surrogatePair
                self.waitLowSurrogate = False
                return
            self.catchNotValidByteCombination()
            self.waitLowSurrogate = False
        if isHighSurrogateCode(charCode):
            self.waitLowSurrogate = True
            self.savedHighSurrogateCode = charCode
            return
        if isLowSurrogateCode(charCode):
            self.catchNotValidByteCombination()
            return
        self.decodedText += chr(charCode)

    def defDynamicWin(self, offset, index):
        if offset is None:
            self.catchNotValidByteCombination()
        else:
            self.wins[1][index] = offset
            self.currentWin = offset


def convertCodeToOffset(winCode):
    if winCode != 0 and winCode < DEF_DYN_WIN_1ST_PRIV_CODE:
        return winCode * WIN_SIZE
    if winCode <= DEF_DYN_WIN_LAST_BMP_CODE:
        return winCode * WIN_SIZE + DEF_DYN_WIN_1ST_PRIV_ADD_OFFSET
    if winCode >= DEF_DYN_WIN_1ST_CROSS_BORDER_CODE:
        crossBorderOffsIndex = winCode - DEF_DYN_WIN_1ST_CROSS_BORDER_CODE
        return DEF_DYN_WIN_CROSS_BORDER_OFFSETS[crossBorderOffsIndex]
    return


def defineDynamicWin(byteCode, winIndex, decoder):
    offs = convertCodeToOffset(byteCode)
    decoder.defDynamicWin(offs, winIndex)


def defineDynamicWinExt(combinedBytes, decoder):
    winIndex = combinedBytes // DEF_EXT_WIN_PARAMS_SPLIT
    winOffsId = combinedBytes % DEF_EXT_WIN_PARAMS_SPLIT
    winOffset = FIRST_NON_BMP_CHAR_CODE + winOffsId * WIN_SIZE
    decoder.defDynamicWin(winOffset, winIndex)


def checkSizeOfByteCombination(leadByte):
    if leadByte == DEFINE_EXTENDED_1BYTE or leadByte == QUOTE_UNICODE_1BYTE:
        return LONG_COMBINATIONS_ADDITIONAL_SIZE
    isQuoteSingleByte = leadByte >= QUOTE_WIN_0_1BYTE and leadByte < TAB_CODE
    isDefineWin = leadByte >= DEFINE_DYN_WIN_0_1BYTE and leadByte < SPACE_CODE
    if isQuoteSingleByte or isDefineWin:
        return 1
    return 0


def checkSizeOfByteCombinationUni(leadByte):
    if leadByte == DEFINE_EXTENDED_UNI or leadByte == QUOTE_UNICODE_UNI:
        return LONG_COMBINATIONS_ADDITIONAL_SIZE
    isChooseWin = leadByte >= CHOOSE_DYN_WIN_0_UNI and leadByte < DEFINE_DYN_WIN_0_UNI
    if isChooseWin or leadByte == RESERVED_UNI:
        return 0
    return 1


def decodeLongByteCombination(tagByte, argsBytes, decoder):
    combinedArgs = int.from_bytes(argsBytes)
    if tagByte == DEFINE_EXTENDED_1BYTE:
        defineDynamicWinExt(combinedArgs, decoder)
    else:
        decoder.decodeUniModeCode(combinedArgs)


def decodeLongByteCombinationUni(tagByte, argsBytes, decoder):
    combinedArgs = int.from_bytes(argsBytes)
    if tagByte == DEFINE_EXTENDED_UNI:
        defineDynamicWinExt(combinedArgs, decoder)
        decoder.unicodeMode = False
    else:
        decoder.decodeUniModeCode(combinedArgs)


def decodeShortByteCombination(tagByte, argByte, decoder):
    arg = int.from_bytes(argByte)
    if tagByte < TAB_CODE:
        winIndex = tagByte - QUOTE_WIN_0_1BYTE
        decoder.decodeByte(arg, winIndex)
    else:
        winIndex = tagByte - DEFINE_DYN_WIN_0_1BYTE
        defineDynamicWin(arg, winIndex, decoder)


def decodeShortByteCombinationUni(tagByte, argByte, decoder):
    arg = int.from_bytes(argByte)
    if tagByte >= DEFINE_DYN_WIN_0_UNI and tagByte < QUOTE_UNICODE_UNI:
        winIndex = tagByte - DEFINE_DYN_WIN_0_UNI
        defineDynamicWin(arg, winIndex, decoder)
        decoder.unicodeMode = False
    else:
        charCode = MOST_SIGNIFICANT_BYTE_MULT * tagByte + arg
        decoder.decodeUniModeCode(charCode)


def decodeSingleByte(byteToDecode, decoder):
    if byteToDecode == BYTE_CHOOSE_UNICODE_MODE:
        decoder.unicodeMode = True
    elif (
        byteToDecode >= CHOOSE_DYN_WIN_0_1BYTE and byteToDecode < DEFINE_DYN_WIN_0_1BYTE
    ):
        winIndex = byteToDecode - CHOOSE_DYN_WIN_0_1BYTE
        decoder.chooseWin(winIndex)
    elif byteToDecode == RESERVED_1BYTE:
        decoder.catchNotValidByteCombination()
    else:
        decoder.decodeByte(byteToDecode)


def checkLeadByteInWaitingLowSurrogate(leadByte, addBytesAmount, decoder):
    if not addBytesAmount:
        isChooseWin = (
            leadByte >= CHOOSE_DYN_WIN_0_1BYTE and leadByte < DEFINE_DYN_WIN_0_1BYTE
        )
        if leadByte == BYTE_CHOOSE_UNICODE_MODE or isChooseWin:
            return
    elif not (leadByte >= QUOTE_WIN_0_1BYTE and leadByte < TAB_CODE):
        return
    decoder.catchNotValidByteCombination()
    decoder.waitLowSurrogate = False


def decodeInUnicodeMode(bytesToDecode, decoder):
    bytesLeft = bytesToDecode
    while len(bytesLeft) and decoder.unicodeMode:
        mostSignifByte = bytesLeft[0]
        additionalBytesAmount = checkSizeOfByteCombinationUni(mostSignifByte)
        additionalBytes = bytesLeft[1 : additionalBytesAmount + 1]
        bytesLeft = bytesLeft[additionalBytesAmount + 1 :]
        if len(additionalBytes) == additionalBytesAmount:
            if additionalBytesAmount > 1:
                decodeLongByteCombinationUni(mostSignifByte, additionalBytes, decoder)
            elif not additionalBytesAmount:
                if mostSignifByte == RESERVED_UNI:
                    decoder.catchNotValidByteCombination()
                    break
                winIndex = mostSignifByte - CHOOSE_DYN_WIN_0_UNI
                decoder.chooseWin(winIndex)
                decoder.unicodeMode = False
            else:
                decodeShortByteCombinationUni(mostSignifByte, additionalBytes, decoder)
        else:
            decoder.catchNotValidByteCombination()
    return bytesLeft


def decodeScsu(bytesToDecode):
    scsuDecoder = scsuDecoderClass()
    bytesLeft = bytesToDecode
    while len(bytesLeft):
        currentByte = bytesLeft[0]
        additionalBytesAmount = checkSizeOfByteCombination(currentByte)
        if scsuDecoder.waitLowSurrogate:
            checkTagInWaitingLowSurrogate(
                currentByte, additionalBytesAmount, scsuDecoder
            )
        additionalBytes = bytesLeft[1 : additionalBytesAmount + 1]
        bytesLeft = bytesLeft[additionalBytesAmount + 1 :]
        if len(additionalBytes) == additionalBytesAmount:
            if additionalBytesAmount > 1:
                decodeLongByteCombination(currentByte, additionalBytes, scsuDecoder)
            elif additionalBytesAmount:
                decodeShortByteCombination(currentByte, additionalBytes, scsuDecoder)
            else:
                decodeSingleByte(currentByte, scsuDecoder)
        else:
            scsuDecoder.catchNotValidByteCombination()
        if scsuDecoder.unicodeMode:
            bytesLeft = decodeInUnicodeMode(bytesLeft, scsuDecoder)
    return scsuDecoder.decodedText
