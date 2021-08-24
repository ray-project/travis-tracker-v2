interface:
	py-ts-interfaces -o js/src/interface.ts ray_ci_tracker/interfaces.py
	sed -i.bak "s/^interface/export interface/g" js/src/interface.ts

data:
	python fetch_and_render.py

site: interface data
	cd js; yarn; yarn build