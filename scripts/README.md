# Repository scripts

Repository-level engineering and documentation tooling lives here.

Current tools include:

- `check_doc_links.py` — validates local Markdown links across the monorepo.
- `update_doc_nav.py` — maintains LiDAR engineering-document navigation.
- `backup_prod_db.sh` — copies the production platform database to this
  machine on demand; see `products/transelect/docs/deployment.md`,
  "Manual database backup".

Product-specific operational scripts belong inside their owning product.

For LiDAR-specific scripts, see:

    products/lidar/scripts/
