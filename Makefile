interface:
	py-ts-interfaces -o js/src/interface.ts ray_ci_tracker/interfaces.py
	sed -i.bak "s/^interface/export interface/g" js/src/interface.ts

data:
	ray-ci download cache_dir
	ray-ci etl cache_dir results.db
	ray-ci analysis results.db js/src/data.json

site: interface data
	cd js; yarn; yarn build