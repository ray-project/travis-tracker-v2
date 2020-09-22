interface:
	py-ts-interfaces -o js/src/interface.ts interfaces.py
	sed -i "" "s/^interface/export interface/g" js/src/interface.ts