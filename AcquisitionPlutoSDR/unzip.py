import os
import pandas as pd
def convert_parquet_to_csv_and_delete(directory):
    # Parcourir tous les fichiers du dossier
    for filename in os.listdir(directory):
        if filename.endswith(".parquet"):
            parquet_file = os.path.join(directory, filename)
            csv_file = os.path.join(directory, filename.replace('.parquet', '.csv'))

            # Lire le fichier Parquet en DataFrame pandas
            df = pd.read_parquet(parquet_file)

            # Convertir le DataFrame en fichier CSV
            df.to_csv(csv_file, index=False)

            print(f"Fichier CSV généré : {csv_file}")

            # Supprimer le fichier Parquet
            os.remove(parquet_file)
            print(f"Fichier Parquet supprimé : {parquet_file}")


# Exemple d'utilisation
# directory = 'C:\\Users\\DEV\\Desktop\\Samuel\\AcquisitionPlutoSDR2\\recordings_temp'  # Spécifiez votre dossier ici
# convert_parquet_to_csv_and_delete(directory)