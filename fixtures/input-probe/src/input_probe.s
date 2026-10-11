; ---------------------------------------------------------------------------
; retro-game-qa fixture: "input-probe"
;
; A deliberately tiny NES ROM whose ONLY purpose is to make controller input
; observable in CPU RAM. It is original source written for this repository
; and is built with ca65. It is NOT a commercial game or a bundled ROM.
;
; Mapper 0 (NROM), 32 KiB PRG + 8 KiB CHR.  No OS/file/interrupt tricks.
;
; ---------------------------------------------------------------------------
; Memory contract (fixed; mirrored in the symbol file and asserted by tests):
;   $0300  frame_lo        16-bit inclusive frame counter, starts at 0, +1/NMI
;   $0301  frame_hi
;   $0302  pad1_held       controller-1 buttons held this frame (1 = held)
;                          A=01 B=02 Select=04 Start=08 Up=10 Down=20 Left=40 Right=80
;   $0303  pad1_prev       buttons held on the previous frame
;   $0304  pad1_press      buttons that went 0->1 this frame  (held & ~prev)
;   $0305  pad1_release    buttons that went 1->0 this frame  (~held & prev)
;   $0306  right_frames    count of frames during which RIGHT was held
;   $0307  a_frames        count of frames during which A was held
;   $0308  signature       rolling checksum, changes as held-buttons change
; ---------------------------------------------------------------------------

.setcpu "6502"

; RAM state block. Declared in a dedicated segment so ld65 emits real labels
; into the .lbl map (with `-Ln`). ld65 emits absolute CPU addresses; use
; segment_base=0 with this fixture's labels.
.segment "RAMVARS"
.export frame_lo, frame_hi, pad1_held, pad1_prev, pad1_press, pad1_release
.export right_frames, a_frames, signature
frame_lo:     .res 1      ; $0300  inclusive frame counter, low byte, +1/NMI
frame_hi:     .res 1      ; $0301  frame counter high byte
pad1_held:    .res 1      ; $0302  buttons held this frame
pad1_prev:    .res 1      ; $0303  buttons held on the previous frame
pad1_press:   .res 1      ; $0304  buttons that went 0->1 this frame
pad1_release: .res 1      ; $0305  buttons that went 1->0 this frame
right_frames: .res 1      ; $0306  frames during which RIGHT was held
a_frames:     .res 1      ; $0307  frames during which A was held
signature:    .res 1      ; $0308  rolling checksum over held-button changes

.assert frame_lo = $0300, error, "RAM contract moved: frame_lo must be $0300"
.assert pad1_held = $0302, error, "RAM contract moved: pad1_held must be $0302"
.assert signature = $0308, error, "RAM contract moved: signature must be $0308"

.segment "ZEROPAGE"
nmi_ready:  .res 1              ; 1 = NMI happened since main loop cleared it

.segment "HEADER"
        .byte "NES", $1A
        .byte $02               ; 2 x 16 KiB PRG banks (32 KiB PRG total)
        .byte $01               ; 1 x 8 KiB CHR bank
        .byte $00               ; flags 6: mapper 0, horizontal mirroring
        .byte $00               ; flags 7
        .byte $00, $00, $00, $00, $00, $00, $00, $00

.segment "CODE"

; ---------------------------------------------------------------------------
reset:
        sei
        cld
        ldx #$40
        stx $4017               ; disable APU frame IRQ
        ldx #$FF
        txs
        inx                     ; x = 0
        stx $2000
        stx $2001
        stx $4010

:       bit $2002               ; wait for first vblank
        bpl :-

        lda #0                  ; clear $0000-$07FF (our state lives at $0300)
        ldx #0
clear_ram:
        sta $0000,x
        sta $0100,x
        sta $0200,x
        sta $0300,x
        sta $0400,x
        sta $0500,x
        sta $0600,x
        sta $0700,x
        inx
        bne clear_ram

:       bit $2002               ; wait for a second vblank
        bpl :-

        lda #%10000000          ; enable NMI
        sta $2000

; ---------------------------------------------------------------------------
main_loop:
        lda #0
        sta nmi_ready
:       lda nmi_ready           ; block until this frame's NMI fired
        beq :-

        lda #1                  ; strobe controller 1
        sta $4016
        lda #0
        sta $4016
        ldx #8
read_pad:
        lda $4016
        lsr a                   ; bit0 -> carry
        ror $0302               ; A ends in bit0 after eight serial reads
        dex
        bne read_pad

        inc $0300               ; frame_lo++
        bne :+
        inc $0301               ; frame_hi++
:

        ; press = held & ~prev
        lda $0303
        eor #$FF
        and $0302
        sta $0304
        ; release = ~held & prev
        lda $0302
        eor #$FF
        and $0303
        sta $0305
        ; prev = held
        lda $0302
        sta $0303

        lda $0302               ; right_frames++
        and #$80                ; RIGHT
        beq :+
        inc $0306
:
        lda $0302               ; a_frames++
        and #$01                ; A
        beq :+
        inc $0307
:
        lda $0308               ; signature rolls with held-state changes
        eor $0302
        clc
        adc #$1D
        sta $0308

        jmp main_loop

; ---------------------------------------------------------------------------
nmi:
        pha
        txa
        pha
        tya
        pha
        lda #1
        sta nmi_ready
        pla
        tay
        pla
        tax
        pla
        rti

irq:
        rti

.segment "VECTORS"
        .word nmi
        .word reset
        .word irq

.segment "CHARS"
        .res 8192, $00
