# Build the controlled NROM test fixture from source.
#
# Produces build/input-probe.nes (legal, redistributable, no copyrighted data)
# and build/input-probe.lbl (linker label map). See src/input_probe.s for the
# fixed RAM contract the QA harness asserts against.
CA65 ?= ca65
LD65 ?= ld65

SRC  := src/input_probe.s
OBJ  := build/input_probe.o
ROM  := build/input-probe.nes
LBL  := build/input-probe.lbl

.PHONY: all builddir check

all: $(ROM)

$(OBJ): $(SRC)
	@mkdir -p build
	$(CA65) -o $(OBJ) $(SRC)

$(ROM): $(OBJ) nes.cfg
	$(LD65) -C nes.cfg -o $(ROM) $(OBJ) -Ln $(LBL)

# Structural sanity check: correct magic, PRG-bank byte, and total size.
check: $(ROM)
	@printf 'magic:  '; xxd -l 4 -p $(ROM)
	@printf 'bank:   '; xxd -s 4 -l 1 -p $(ROM)
	@printf 'chr:    '; xxd -s 5 -l 1 -p $(ROM)
	@printf 'size:   '; stat -c%s $(ROM)
	@test "$$(stat -c%s $(ROM))" = "40976" || { echo "BAD SIZE"; exit 1; }
	@test "$$(xxd -l 4 -p $(ROM))" = "4e45531a" || { echo "BAD MAGIC"; exit 1; }
	@test "$$(xxd -s 4 -l 1 -p $(ROM))" = "02" || { echo "BAD PRG BANK BYTE"; exit 1; }
	@echo "fixture ROM OK"
